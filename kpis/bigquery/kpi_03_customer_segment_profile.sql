-- KPI 3: Standardised customer segment profile
-- Definition: per standardised customer segment, the number of customers and the average order value (AOV).
-- Measure: AOV = net order value / distinct completed orders.
--    Net order value = SUM(fact_order_items.line_total) - approved refunds (each refund capped at its line_total).
-- Numerator: net order value of completed orders placed by customers in the segment.
-- Denominator: distinct completed orders (order_status = 'Completed') that have at least one valid order line.
-- Data quality: resolved in silver before this KPI: customer_segment standardised from mixed spelling and casing
--    (e.g. 'glod' -> Gold, 'silverr' -> Silver, 'broze' / 'BRONZE' -> Bronze; blank -> Unknown); exact duplicate
--    customer rows removed; order status labels standardised; line_total recomputed. Orders from customer ids
--    missing from the customer file are kept under segment 'Unknown' (customer_count 0, buying_customers =
--    distinct unmatched ids) so the segment totals still add up to all completed orders.
-- Inclusions: customer_count counts every customer in dim_customer, whether or not they ordered.
--    buying_customers counts distinct customer ids with at least one completed order.
-- Exclusions: Cancelled, Pending and Returned orders; refunds with return_status Pending or Rejected or no amount;
--    completed orders with no valid lines (all lines quarantined, value unknown).
-- Alternatives: (1) gross AOV, before refunds (higher in every segment). (2) average per customer instead of per
--    order (net value / buying customers). (3) customer_count of buying customers only.
-- Assumptions: near-duplicate customers (same email and phone, dup_group_id) are counted separately, not merged.
--    dim_customer has one version per customer today, so the segment is the current one.
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
),
segment_customers AS (
    SELECT customer_segment, COUNTIF(customer_key <> -1) AS customer_count
    FROM dim_customer
    GROUP BY customer_segment
),
segment_orders AS (
    SELECT c.customer_segment,
           COUNT(DISTINCT o.customer_id_source) AS buying_customers,
           COUNT(DISTINCT o.order_id) AS completed_orders,
           SUM(o.net_value) AS net_order_value
    FROM completed_orders AS o
    JOIN dim_customer AS c ON c.customer_key = o.customer_key
    GROUP BY c.customer_segment
)
SELECT s.customer_segment,
       s.customer_count,
       COALESCE(o.buying_customers, 0) AS buying_customers,
       COALESCE(o.completed_orders, 0) AS completed_orders,
       ROUND(COALESCE(o.net_order_value, 0), 2) AS net_order_value,
       ROUND(SAFE_DIVIDE(o.net_order_value, o.completed_orders), 2) AS avg_order_value
FROM segment_customers AS s
LEFT JOIN segment_orders AS o ON o.customer_segment = s.customer_segment
ORDER BY CASE s.customer_segment
             WHEN 'Platinum' THEN 1 WHEN 'Gold' THEN 2 WHEN 'Silver' THEN 3
             WHEN 'Bronze' THEN 4 ELSE 5
         END;
