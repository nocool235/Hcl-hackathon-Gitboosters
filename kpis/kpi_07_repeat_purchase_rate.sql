-- KPI 7: Repeat-purchase rate
-- Definition: share of customers who place another completed order within repeat_window_days (config, read from the run_params table) of
--    their first completed order.
-- Numerator: customers with at least one other completed order dated from their first order date up to
--    first order date + window (a second order on the same day counts).
-- Denominator: customers with at least one completed order (order_status = 'Completed').
-- Primary: FULL_WINDOW, restricted to customers whose first order date + window <= reference date, so every
--    customer has had the full window to repeat. ALL_CUSTOMERS includes recent first-time customers who have not
--    had 90 days yet, which pulls the rate down; it is reported for comparison.
-- Data quality: resolved in silver before this KPI: order status labels standardised; order dates in mixed formats
--    parsed (63 ambiguous slash dates read as MM/DD and flagged; a misread date can move an order in or out of
--    the 90-day window); exact duplicate orders removed, so a duplicated order is never counted as a repeat.
--    Orders whose customer id is missing from the customer file (customer_key = -1) cannot be linked into a
--    purchase history and are excluded. Near-duplicate customers are counted separately (not merged).
-- Exclusions: Cancelled, Pending and Returned orders.
-- Alternatives: (1) ALL_CUSTOMERS as the headline (simpler, but biased down by customers still inside their
--    window). (2) count Returned orders as purchases. (3) require the repeat order strictly after the first day.
-- Assumptions: reference date = reference_date (config, read from the run_params table); when null, the latest order
--    date in fact_orders (never today). First order = earliest order_date, ties broken by order_id.
WITH params AS (
    SELECT (SELECT CAST(value AS INTEGER) FROM run_params WHERE param = 'repeat_window_days') AS window_days,
           COALESCE((SELECT value FROM run_params WHERE param = 'reference_date'), (SELECT MAX(order_date) FROM fact_orders)) AS reference_date
),
completed AS (
    SELECT customer_key, order_id, order_date
    FROM fact_orders
    WHERE order_status = 'Completed' AND customer_key <> -1
),
first_orders AS (
    SELECT customer_key, order_id AS first_order_id, order_date AS first_order_date
    FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY customer_key ORDER BY order_date, order_id) AS rn
        FROM completed
    )
    WHERE rn = 1
),
customers AS (
    SELECT f.customer_key,
           date(f.first_order_date, '+' || p.window_days || ' days') <= p.reference_date
               AS has_full_window,
           COUNT(c.order_id) > 0 AS is_repeat
    FROM first_orders AS f
    CROSS JOIN params AS p
    LEFT JOIN completed AS c
        ON c.customer_key = f.customer_key
       AND c.order_id <> f.first_order_id
       AND c.order_date BETWEEN f.first_order_date
                            AND date(f.first_order_date, '+' || p.window_days || ' days')
    GROUP BY f.customer_key, f.first_order_date, p.window_days, p.reference_date
)
SELECT 'FULL_WINDOW' AS cohort,
       TRUE AS is_primary,
       COUNT(*) AS customers_denominator,
       SUM(CASE WHEN is_repeat THEN 1 ELSE 0 END) AS repeat_customers,
       ROUND(100.0 * (1.0 * (SUM(CASE WHEN is_repeat THEN 1 ELSE 0 END)) / NULLIF(COUNT(*), 0)), 2) AS repeat_rate_pct,
       (SELECT window_days FROM params) AS window_days,
       (SELECT reference_date FROM params) AS reference_date
FROM customers
WHERE has_full_window
UNION ALL
SELECT 'ALL_CUSTOMERS',
       FALSE,
       COUNT(*),
       SUM(CASE WHEN is_repeat THEN 1 ELSE 0 END),
       ROUND(100.0 * (1.0 * (SUM(CASE WHEN is_repeat THEN 1 ELSE 0 END)) / NULLIF(COUNT(*), 0)), 2),
       (SELECT window_days FROM params),
       (SELECT reference_date FROM params)
FROM customers
ORDER BY is_primary DESC;
