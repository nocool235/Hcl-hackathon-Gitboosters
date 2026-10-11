-- KPI 2 (companion): Customer references excluded from the ranking
-- Definition: completed-order value that KPI 2 keeps out of its ranking, with counts, so it is reported, not lost.
--    Part of KPI 2, not a separate KPI.
-- Measure: same net value as KPI 2 (line_total - approved refunds, capped per line), completed orders only.
-- ORPHAN_CUSTOMER: orders whose customer id is not in the customer file (customer_key = -1).
--    customer_references = distinct unmatched source customer ids.
-- AMBIGUOUS_CUSTOMER: orders from near-duplicate customers (same normalised email and phone under different ids,
--    dup_group_id set). customer_references = distinct customer ids; dup_groups = distinct duplicate groups.
-- Exclusions: Cancelled, Pending and Returned orders; refunds with return_status Pending or Rejected or no amount;
--    completed orders with no valid lines.
-- Assumptions: both rows are always returned (zeros when there are no exceptions).
WITH approved_refunds AS (
    SELECT order_item_id, SUM(refund_amount) AS refund_amount
    FROM fact_returns
    WHERE return_status = 'Approved' AND refund_amount IS NOT NULL
    GROUP BY order_item_id
),
completed_orders AS (
    SELECT o.order_id, o.customer_key, o.customer_id_source,
           SUM(i.line_total - LEAST(COALESCE(r.refund_amount, 0), i.line_total)) AS net_value
    FROM fact_orders AS o
    JOIN fact_order_items AS i ON i.order_id = o.order_id
    LEFT JOIN approved_refunds AS r ON r.order_item_id = i.order_item_id
    WHERE o.order_status = 'Completed'
    GROUP BY o.order_id, o.customer_key, o.customer_id_source
)
SELECT 'ORPHAN_CUSTOMER' AS reference_type,
       COUNT(DISTINCT o.customer_id_source) AS customer_references,
       0 AS dup_groups,
       COUNT(*) AS completed_orders,
       ROUND(COALESCE(SUM(o.net_value), 0), 2) AS net_value
FROM completed_orders AS o
WHERE o.customer_key = -1
UNION ALL
SELECT 'AMBIGUOUS_CUSTOMER',
       COUNT(DISTINCT c.customer_id),
       COUNT(DISTINCT c.dup_group_id),
       COUNT(*),
       ROUND(COALESCE(SUM(o.net_value), 0), 2)
FROM completed_orders AS o
JOIN dim_customer AS c ON c.customer_key = o.customer_key
WHERE c.customer_key <> -1 AND c.dup_group_id IS NOT NULL
ORDER BY reference_type DESC;
