-- KPI 2: Top 10 customers by net lifetime value
-- Definition: the 10 customers with the highest net lifetime value (LTV) from completed orders.
-- Measure: net LTV = SUM(line_total) - approved refunds (each capped at its line_total) over the customer's
--    completed orders (order_status = 'Completed').
-- Ranking: net LTV descending, then completed order count descending, then customer_key ascending.
-- Data quality: resolved in silver before this KPI: exact duplicate customer rows removed; order status labels
--    standardised (e.g. 'complted' -> Completed); line_total recomputed. Orphaned references (orders whose
--    customer id is not in the customer file, customer_key = -1) and ambiguous references (near-duplicate
--    customers: same normalised email and phone under different ids, dup_group_id set) are kept and flagged
--    in gold, not dropped.
-- Orphaned and ambiguous references: decision: kept out of the ranking and reported with their count and value in
--    kpi_02b_customer_reference_exceptions, so a customer is never ranked on a guessed identity.
-- Inclusions: customers present in dim_customer with no near-duplicate flag.
-- Exclusions: Cancelled, Pending and Returned orders; refunds with return_status Pending or Rejected or no amount;
--    completed orders with no valid lines.
-- Alternatives: (1) merge each near-duplicate group into one customer and rank it (irreversible, and the source
--    gives no proof they are the same person). (2) rank orphaned ids as their own customers by source id
--    (no name or segment is known for them). (3) include Returned orders net of their refunds.
-- Assumptions: one dim_customer version per customer today, so customer_key identifies a customer.
WITH approved_refunds AS (
    SELECT order_item_id, SUM(refund_amount) AS refund_amount
    FROM fact_returns
    WHERE return_status = 'Approved' AND refund_amount IS NOT NULL
    GROUP BY order_item_id
),
completed_orders AS (
    SELECT o.order_id, o.customer_key,
           SUM(i.line_total - MIN(COALESCE(r.refund_amount, 0), CAST(i.line_total AS REAL))) AS net_value
    FROM fact_orders AS o
    JOIN fact_order_items AS i ON i.order_id = o.order_id
    LEFT JOIN approved_refunds AS r ON r.order_item_id = i.order_item_id
    WHERE o.order_status = 'Completed'
    GROUP BY o.order_id, o.customer_key
),
customer_ltv AS (
    SELECT c.customer_key, c.customer_id,
           c.first_name || ' ' || c.last_name AS customer_name,
           c.customer_segment,
           COUNT(*) AS completed_orders,
           ROUND(SUM(o.net_value), 2) AS net_lifetime_value
    FROM completed_orders AS o
    JOIN dim_customer AS c ON c.customer_key = o.customer_key
    WHERE c.customer_key <> -1 AND c.dup_group_id IS NULL
    GROUP BY c.customer_key, c.customer_id, c.first_name, c.last_name, c.customer_segment
),
ranked AS (
    SELECT ROW_NUMBER() OVER (
               ORDER BY net_lifetime_value DESC, completed_orders DESC, customer_key
           ) AS ltv_rank,
           customer_ltv.*
    FROM customer_ltv
)
SELECT ltv_rank, customer_id, customer_key, customer_name, customer_segment,
       completed_orders, net_lifetime_value
FROM ranked
WHERE ltv_rank <= 10
ORDER BY ltv_rank;
