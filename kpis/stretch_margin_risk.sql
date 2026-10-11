-- Stretch: Margin risk report
-- Definition: products sold at a loss, i.e. order lines where the product's cost_price exceeds the effective
--    selling price per unit after discount.
-- Measure: effective selling price = line_total / quantity (recomputed line value after discount).
--    affected_quantity and affected_revenue (quantity and revenue exposed) sum the lines sold below cost.
--    margin_shortfall = SUM(cost_price * quantity - line_total) over those lines (the loss versus cost).
-- Data quality: resolved in silver before this report: duplicate and conflicting product records (one cost per
--    product); line_total recomputed from quantity, unit price and discount; order lines with an invalid
--    quantity, price or discount quarantined. Products whose list price is invalid (price_issue) keep a NULL list
--    price; the line's own price is used here, so they are still checked.
-- Inclusions: lines on Completed or Returned orders (same revenue scope as KPI 1).
-- Exclusions: Cancelled and Pending orders; products missing from the product file (product_key = -1);
--    products without a cost_price.
-- Alternatives: (1) compare cost with the product list price after discount instead of the line's own price.
--    (2) include Cancelled and Pending orders (counts sales that did not happen). (3) subtract refunds.
-- Assumptions: refunds are not subtracted (this is a pricing check on the sale, not net revenue).
--    cost_price is the current product cost from dim_product; there is no cost history.
WITH lines AS (
    SELECT i.product_key, i.quantity, i.line_total,
           (1.0 * (i.line_total) / NULLIF(i.quantity, 0)) AS net_unit_price
    FROM fact_order_items AS i
    JOIN fact_orders AS o ON o.order_id = i.order_id
    WHERE o.order_status IN ('Completed', 'Returned') AND i.product_key <> -1
)
SELECT p.product_id,
       p.product_name,
       p.category,
       p.cost_price,
       ROUND(MIN(l.net_unit_price), 2) AS min_net_unit_price,
       ROUND(MAX(l.net_unit_price), 2) AS max_net_unit_price,
       COUNT(*) AS affected_lines,
       SUM(l.quantity) AS affected_quantity,
       ROUND(SUM(l.line_total), 2) AS affected_revenue,
       ROUND(SUM(p.cost_price * l.quantity - l.line_total), 2) AS margin_shortfall
FROM lines AS l
JOIN dim_product AS p ON p.product_key = l.product_key
WHERE p.cost_price IS NOT NULL AND CAST(p.cost_price AS REAL) > l.net_unit_price
GROUP BY p.product_key, p.product_id, p.product_name, p.category, p.cost_price
ORDER BY margin_shortfall DESC, p.product_id;
