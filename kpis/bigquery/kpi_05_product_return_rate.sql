-- KPI 5: Product return rate (top 10 and bottom 10)
-- Definition: return rate per product = returned quantity / ordered quantity.
-- Numerator: returned quantity of returns not Rejected (Approved or Pending), on lines in the denominator.
-- Denominator: ordered quantity on lines of Completed or Returned orders (goods that reached the customer).
-- Threshold: only products with ordered quantity >= @return_rate_min_volume (config medallion.return_rate_min_volume)
--    are ranked, so low-sales products do not distort the ranking.
-- Data quality: returns.csv has no quantity column, so the pipeline derives it: the full line quantity when the
--    refund covers the line value (FULL), otherwise quantity * refund / line value (PROPORTIONAL, can be
--    fractional); returns with no refund amount get an unknown quantity (counted in returns_unknown_qty, adding 0).
--    Also resolved in silver: duplicate return rows removed; return status labels standardised; duplicate and
--    conflicting product records resolved. 29 returns dated before their order are kept (dates do not affect a
--    rate). Returns whose order item is unknown cannot be tied to a product and are excluded.
-- Output: ranking TOP = highest return rate, BOTTOM = lowest. Ties: higher ordered quantity first, then product_id.
--    A product can appear in both lists when fewer than 20 products qualify (see products_qualifying).
-- Exclusions: Cancelled and Pending orders; Rejected returns; lines for products missing from the product file
--    (product_key = -1).
-- Alternatives: (1) Approved returns only (stricter; a Pending return is still goods coming back). (2) count-based
--    rate: returned lines / ordered lines. (3) all order statuses in the denominator (counts goods never shipped).
WITH delivered_lines AS (
    SELECT i.order_item_id, i.product_key, i.quantity
    FROM fact_order_items AS i
    JOIN fact_orders AS o ON o.order_id = i.order_id
    WHERE o.order_status IN ('Completed', 'Returned') AND i.product_key <> -1
),
line_returns AS (
    SELECT order_item_id,
           COUNT(*) AS returns,
           COUNTIF(returned_quantity IS NULL) AS returns_unknown_qty,
           COALESCE(SUM(returned_quantity), 0) AS returned_qty
    FROM fact_returns
    WHERE return_status <> 'Rejected'
    GROUP BY order_item_id
),
product_totals AS (
    SELECT l.product_key,
           SUM(l.quantity) AS ordered_qty,
           COALESCE(SUM(r.returned_qty), 0) AS returned_qty,
           COALESCE(SUM(r.returns), 0) AS returns,
           COALESCE(SUM(r.returns_unknown_qty), 0) AS returns_unknown_qty
    FROM delivered_lines AS l
    LEFT JOIN line_returns AS r ON r.order_item_id = l.order_item_id
    GROUP BY l.product_key
),
qualifying AS (
    SELECT p.product_id, p.product_name, p.category, t.ordered_qty,
           ROUND(t.returned_qty, 4) AS returned_qty, t.returns, t.returns_unknown_qty,
           SAFE_DIVIDE(t.returned_qty, t.ordered_qty) AS return_rate,
           COUNT(*) OVER () AS products_qualifying
    FROM product_totals AS t
    JOIN dim_product AS p ON p.product_key = t.product_key
    WHERE t.ordered_qty >= @return_rate_min_volume
),
ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (ORDER BY return_rate DESC, ordered_qty DESC, product_id) AS top_rank,
           ROW_NUMBER() OVER (ORDER BY return_rate ASC, ordered_qty DESC, product_id) AS bottom_rank
    FROM qualifying
)
SELECT ranking, rank_in_list, product_id, product_name, category, ordered_qty, returned_qty,
       return_rate_pct, returns, returns_unknown_qty, products_qualifying
FROM (
    SELECT 'TOP' AS ranking, top_rank AS rank_in_list, product_id, product_name, category, ordered_qty,
           returned_qty, ROUND(100 * return_rate, 2) AS return_rate_pct, returns, returns_unknown_qty,
           products_qualifying
    FROM ranked WHERE top_rank <= 10
    UNION ALL
    SELECT 'BOTTOM', bottom_rank, product_id, product_name, category, ordered_qty,
           returned_qty, ROUND(100 * return_rate, 2), returns, returns_unknown_qty,
           products_qualifying
    FROM ranked WHERE bottom_rank <= 10
)
ORDER BY CASE ranking WHEN 'TOP' THEN 1 ELSE 2 END, rank_in_list;
