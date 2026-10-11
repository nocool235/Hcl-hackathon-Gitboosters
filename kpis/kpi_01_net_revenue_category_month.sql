-- KPI 1: Net revenue by product category per month
-- Definition: net revenue per order month (YYYY-MM of the order date) and standardised product category.
-- Measure: net revenue = recomputed line revenue after discount (fact_order_items.line_total) - approved refunds.
--    Each refund is capped at its line_total, so a line never goes below zero.
-- Data quality: resolved in silver before this KPI: duplicate and conflicting product records (one winner per
--    product_id, the losers quarantined); category labels standardised (e.g. 'electornics' -> Electronics,
--    'homeandkitchen' -> Home & Kitchen); a blank category on 5 products (P008, P017, P054, P059, P066) filled from
--    their sub-category, which maps to exactly one category across all other products (flagged in
--    dim_product.category_inferred); line_total recomputed from quantity, unit price and discount because 29
--    source totals were wrong; order dates in mixed formats parsed (63 slash dates with both parts <= 12 read as
--    MM/DD and flagged, which can move an order between months); lines with quantity <= 0, a missing or negative
--    price, or a discount outside 0-100 quarantined. Handled here: refunds above their line value are capped.
-- Inclusions: lines on orders with status Completed or Returned. Lines for products missing from the product
--    file are kept under category 'Unknown' (after the category fill, these are the only Unknown lines).
-- Exclusions: Cancelled and Pending orders (and refunds on their lines, since their revenue is never counted);
--    lines whose order is missing from fact_orders (status unknown); refunds with return_status Pending or
--    Rejected or no amount; returns whose order item is unknown.
-- Returned orders: kept at full line revenue, and their approved refunds are subtracted once, line by line.
--    Order status is never used to remove revenue, so a refund cannot be subtracted twice.
--    A Returned order with no approved refund keeps its full revenue.
-- Refund timing: refunds are attributed to the original order month, not the return month.
-- Alternatives: (1) attribute refunds to the return_date month (cash view); that moves refunds into later months
--    and puts the 29 returns dated before their order in a month earlier than the sale. (2) Count Completed
--    orders only, dropping Returned orders and their refunds; this lowers revenue and hides refund activity.
-- Assumptions: source_line_total is ignored. Payment rows with status Refunded are not used: fact_returns is the
--    single refund source, and using both would double count.
WITH approved_refunds AS (
    SELECT order_item_id, SUM(refund_amount) AS refund_amount
    FROM fact_returns
    WHERE return_status = 'Approved' AND refund_amount IS NOT NULL
    GROUP BY order_item_id
),
scoped_lines AS (
    SELECT substr(o.order_date, 1, 7) AS order_month,
           p.category,
           i.order_id,
           i.line_total,
           MIN(COALESCE(r.refund_amount, 0), CAST(i.line_total AS REAL)) AS refund
    FROM fact_order_items AS i
    JOIN fact_orders AS o ON o.order_id = i.order_id
    JOIN dim_product AS p ON p.product_key = i.product_key
    LEFT JOIN approved_refunds AS r ON r.order_item_id = i.order_item_id
    WHERE o.order_status IN ('Completed', 'Returned')
)
SELECT order_month,
       category,
       COUNT(DISTINCT order_id) AS orders,
       COUNT(*) AS order_lines,
       ROUND(SUM(line_total), 2) AS gross_revenue,
       ROUND(SUM(refund), 2) AS refunds,
       ROUND(SUM(line_total - refund), 2) AS net_revenue
FROM scoped_lines
GROUP BY order_month, category
ORDER BY order_month, category;
