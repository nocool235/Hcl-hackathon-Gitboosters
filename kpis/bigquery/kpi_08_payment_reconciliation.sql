-- KPI 8: Payment reconciliation per order
-- Definition: for each order, successful payments compared with the computed order total, with anomaly flags.
-- Measure: difference = paid_amount - order_total, where paid_amount = SUM(amount) of payment_status 'Success'
--    and order_total = SUM(fact_order_items.line_total) (recomputed lines, before refunds).
-- Status (first match wins): ORPHAN_PAYMENT (payments for an order id missing from fact_orders);
--    NO_SUCCESSFUL_PAYMENT; NO_VALID_LINES (order has no valid lines, total unknown);
--    UNDERPAID (paid < total - tolerance); OVERPAID (paid > total + tolerance); else MATCHED.
--    tolerance = @payment_tolerance (config medallion.payment_tolerance).
-- Flags: duplicate_payment = a payment row recorded twice: an exact duplicate removed in silver
--    (quarantined_duplicate_rows, from quarantine_payments) or two Success rows with the same amount in gold.
--    conflicting_payments = more than one payment row with different amounts or statuses, or a conflicting
--    duplicate quarantined in silver (quarantined_conflicting_rows).
-- Data quality: resolved in silver before this KPI: payment amounts in mixed formats (e.g. '₹210,054.96',
--    '73078.38 INR') parsed to numbers; payment status labels standardised (e.g. 'SUCCESS', 'Succeded' ->
--    Success); exact duplicate payment rows removed and quarantined (counted back here, so they are flagged
--    rather than lost); order totals use recomputed line_total. Payments whose order is missing are kept.
-- Double counting: payments, order lines and quarantined rows are each aggregated to one row per order before
--    they are joined.
-- Inclusions: every order whatever its status (order_status is shown, so filter to Completed to reconcile
--    recognised revenue), plus orphan payments.
-- Exclusions: Failed, Pending and Refunded payments do not count toward paid_amount (they are still counted in
--    payment_rows).
-- Alternatives: (1) compare with the order total net of approved refunds. (2) count Pending payments as paid.
--    (3) a different tolerance (config).
-- Order: exceptions first, then MATCHED, each by order_id.
WITH order_totals AS (
    SELECT order_id, COUNT(*) AS line_count, SUM(line_total) AS order_total
    FROM fact_order_items
    GROUP BY order_id
),
order_payments AS (
    SELECT order_id,
           COUNT(*) AS payment_rows,
           COUNTIF(payment_status = 'Success') AS success_rows,
           SUM(IF(payment_status = 'Success', amount, 0)) AS paid_amount,
           COUNT(DISTINCT IF(payment_status = 'Success', amount, NULL)) AS success_amounts,
           COUNT(DISTINCT amount) AS distinct_amounts,
           COUNT(DISTINCT payment_status) AS distinct_statuses
    FROM fact_payments
    GROUP BY order_id
),
quarantined AS (
    SELECT TRIM(JSON_VALUE(raw_payload, '$.order_id')) AS order_id,
           COUNTIF(reason_code = 'DUPLICATE_EXACT') AS duplicate_rows,
           COUNTIF(reason_code = 'DUPLICATE_CONFLICT') AS conflicting_rows
    FROM quarantine_payments
    WHERE reason_code IN ('DUPLICATE_EXACT', 'DUPLICATE_CONFLICT')
    GROUP BY order_id
),
all_orders AS (
    SELECT order_id, order_status FROM fact_orders
    UNION ALL
    SELECT p.order_id, CAST(NULL AS STRING)
    FROM order_payments AS p
    LEFT JOIN fact_orders AS o ON o.order_id = p.order_id
    WHERE o.order_id IS NULL
),
reconciled AS (
    SELECT a.order_id,
           a.order_status,
           COALESCE(t.line_count, 0) AS line_count,
           ROUND(t.order_total, 2) AS order_total,
           COALESCE(p.payment_rows, 0) AS payment_rows,
           COALESCE(p.success_rows, 0) AS success_rows,
           ROUND(COALESCE(p.paid_amount, 0), 2) AS paid_amount,
           ROUND(COALESCE(p.paid_amount, 0) - t.order_total, 2) AS difference,
           CASE
               WHEN a.order_status IS NULL THEN 'ORPHAN_PAYMENT'
               WHEN COALESCE(p.success_rows, 0) = 0 THEN 'NO_SUCCESSFUL_PAYMENT'
               WHEN t.order_total IS NULL THEN 'NO_VALID_LINES'
               WHEN p.paid_amount < t.order_total - @payment_tolerance THEN 'UNDERPAID'
               WHEN p.paid_amount > t.order_total + @payment_tolerance THEN 'OVERPAID'
               ELSE 'MATCHED'
           END AS reconciliation_status,
           COALESCE(q.duplicate_rows, 0) AS quarantined_duplicate_rows,
           COALESCE(q.conflicting_rows, 0) AS quarantined_conflicting_rows,
           COALESCE(q.duplicate_rows, 0) > 0
               OR COALESCE(p.success_rows > 1 AND p.success_amounts = 1, FALSE) AS duplicate_payment,
           COALESCE(q.conflicting_rows, 0) > 0
               OR COALESCE(p.payment_rows > 1
                           AND (p.distinct_amounts > 1 OR p.distinct_statuses > 1), FALSE)
               AS conflicting_payments
    FROM all_orders AS a
    LEFT JOIN order_totals AS t ON t.order_id = a.order_id
    LEFT JOIN order_payments AS p ON p.order_id = a.order_id
    LEFT JOIN quarantined AS q ON q.order_id = a.order_id
)
SELECT *
FROM reconciled
ORDER BY reconciliation_status = 'MATCHED', reconciliation_status, order_id;
