-- KPI 4: Month-over-month order volume and net revenue growth by channel
-- Definition: per channel and calendar month, order count and net revenue, with growth versus the previous month.
-- Measure: growth_pct = 100 * (this month - previous month) / previous month, previous month taken with the LAG()
--    window function.
-- Calendar: every month from the first to the last month with an in-scope order, for every channel, so months
--    with no orders appear as 0 and LAG() always compares adjacent months.
-- Growth rules: previous month 0 -> growth NULL, flag PRIOR_MONTH_ZERO. Previous net revenue below 0 -> growth
--    NULL, flag PRIOR_MONTH_NEGATIVE. First month of the calendar -> growth NULL, flag FIRST_MONTH.
-- Data quality: resolved in silver before this KPI: channel labels standardised to Web / App / Store
--    (e.g. 'web', 'APP', 'instore' -> Store); order status labels standardised; order dates in mixed formats
--    parsed (63 ambiguous slash dates read as MM/DD and flagged, which can move an order between months);
--    line_total recomputed. 6 orders dated 2020-2022 are valid dates kept as stated (cause unknown).
-- Inclusions: orders with status Completed or Returned (same scope as KPI 1). Orders with no valid lines count
--    toward volume with 0 revenue.
-- Exclusions: Cancelled and Pending orders; refunds with return_status Pending or Rejected or no amount.
-- Alternatives: (1) compare only months that have orders (skipping empty months) - rejected, because growth would
--    then compare non-adjacent months. (2) Completed orders only. (3) gross revenue before refunds.
-- Assumptions: net revenue = line_total - approved refunds (capped per line), refunds in the order month.
--    Because of the 2020-2022 orders the calendar starts in 2020-10; filter by month for 2024-2025 trading.
WITH approved_refunds AS (
    SELECT order_item_id, SUM(refund_amount) AS refund_amount
    FROM fact_returns
    WHERE return_status = 'Approved' AND refund_amount IS NOT NULL
    GROUP BY order_item_id
),
scoped_orders AS (
    SELECT o.order_id, o.channel, FORMAT_DATE('%Y-%m', o.order_date) AS order_month,
           COALESCE(SUM(i.line_total - LEAST(COALESCE(r.refund_amount, 0), i.line_total)), 0)
               AS net_value
    FROM fact_orders AS o
    LEFT JOIN fact_order_items AS i ON i.order_id = o.order_id
    LEFT JOIN approved_refunds AS r ON r.order_item_id = i.order_item_id
    WHERE o.order_status IN ('Completed', 'Returned')
    GROUP BY o.order_id, o.channel, order_month
),
months AS (
    SELECT DISTINCT d.year_month AS order_month
    FROM dim_date AS d
    WHERE d.year_month BETWEEN (SELECT MIN(order_month) FROM scoped_orders)
                           AND (SELECT MAX(order_month) FROM scoped_orders)
),
channels AS (
    SELECT DISTINCT channel FROM fact_orders WHERE channel IS NOT NULL
),
monthly AS (
    SELECT c.channel, m.order_month,
           COUNT(s.order_id) AS order_count,
           ROUND(COALESCE(SUM(s.net_value), 0), 2) AS net_revenue
    FROM channels AS c
    CROSS JOIN months AS m
    LEFT JOIN scoped_orders AS s ON s.channel = c.channel AND s.order_month = m.order_month
    GROUP BY c.channel, m.order_month
),
lagged AS (
    SELECT *,
           LAG(order_count) OVER w AS prev_order_count,
           LAG(net_revenue) OVER w AS prev_net_revenue
    FROM monthly
    WINDOW w AS (PARTITION BY channel ORDER BY order_month)
)
SELECT channel,
       order_month,
       order_count,
       prev_order_count,
       CASE WHEN prev_order_count > 0
            THEN ROUND(100 * (order_count - prev_order_count) / prev_order_count, 2)
       END AS order_growth_pct,
       CASE WHEN prev_order_count IS NULL THEN 'FIRST_MONTH'
            WHEN prev_order_count = 0 THEN 'PRIOR_MONTH_ZERO'
       END AS order_growth_flag,
       net_revenue,
       prev_net_revenue,
       CASE WHEN prev_net_revenue > 0
            THEN ROUND(100 * (net_revenue - prev_net_revenue) / prev_net_revenue, 2)
       END AS revenue_growth_pct,
       CASE WHEN prev_net_revenue IS NULL THEN 'FIRST_MONTH'
            WHEN prev_net_revenue = 0 THEN 'PRIOR_MONTH_ZERO'
            WHEN prev_net_revenue < 0 THEN 'PRIOR_MONTH_NEGATIVE'
       END AS revenue_growth_flag
FROM lagged
ORDER BY channel, order_month;
