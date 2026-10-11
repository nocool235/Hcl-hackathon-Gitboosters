-- KPI 6: Supplier performance scorecard
-- Definition: per supplier, net revenue from its products, the average return rate of its products and its
--    quality rating normalised to 0-1, combined into a 0-1 composite score and ranked.
-- Data quality: ratings were entered on an inconsistent scale: 15 suppliers are rated 1.6-5.0 and 3 are rated
--    7.5-9.4, i.e. some out of 5 and some out of 10. Each rating is normalised on its own scale here: rating > 5
--    -> out of 10, otherwise out of 5 (rating_scale). The pipeline's rating_norm divides every rating by 10,
--    which would halve every 5-point rating, so it is not used. Also resolved in silver: conflicting duplicate
--    supplier rows (S004 under two names, one quarantined); duplicate and conflicting product records.
-- Measures: net_revenue = line_total - approved refunds (capped per line) on Completed or Returned orders, for the
--    supplier's products (same scope as KPI 1).
--    avg_product_return_rate = unweighted average of the KPI 5 return rate over the supplier's products that meet
--    return_rate_min_volume (config, read from the run_params table); products_rated shows how many products that is.
-- Composite weighting: 0.40 revenue + 0.30 returns + 0.30 rating, each component scaled 0-1:
--    revenue_score = net_revenue / highest supplier net_revenue;
--    return_score = 1 - avg_product_return_rate / highest supplier average (fewer returns scores higher);
--    rating_score = rating / rating_scale.
--    A missing component (no product meets the volume threshold, or no rating) is left out and the remaining
--    weights are rescaled to sum to 1; components_used shows how many were used.
-- Ranking: composite_score descending, then supplier_id.
-- Exclusions: products whose supplier is missing from the supplier file (supplier_key = -1) and order lines for
--    unknown products; Cancelled and Pending orders; Rejected returns in the return rate.
-- Alternatives: (1) one scale for every supplier (all out of 10), which halves the 5-point ratings. (2) other
--    weights, e.g. 0.50 / 0.30 / 0.20. (3) revenue as share of total revenue (then revenue barely moves the score
--    unless rescaled). (4) a 10-point supplier rated 5 or below would be misread as out of 5; the data gives no
--    way to tell, so this is the interim assumption.
WITH approved_refunds AS (
    SELECT order_item_id, SUM(refund_amount) AS refund_amount
    FROM fact_returns
    WHERE return_status = 'Approved' AND refund_amount IS NOT NULL
    GROUP BY order_item_id
),
line_returns AS (
    SELECT order_item_id, COALESCE(SUM(returned_quantity), 0) AS returned_qty
    FROM fact_returns
    WHERE return_status <> 'Rejected'
    GROUP BY order_item_id
),
delivered_lines AS (
    SELECT i.product_key, i.quantity,
           i.line_total - MIN(COALESCE(f.refund_amount, 0), CAST(i.line_total AS REAL)) AS net_line,
           COALESCE(r.returned_qty, 0) AS returned_qty
    FROM fact_order_items AS i
    JOIN fact_orders AS o ON o.order_id = i.order_id
    LEFT JOIN approved_refunds AS f ON f.order_item_id = i.order_item_id
    LEFT JOIN line_returns AS r ON r.order_item_id = i.order_item_id
    WHERE o.order_status IN ('Completed', 'Returned') AND i.product_key <> -1
),
product_totals AS (
    SELECT product_key,
           SUM(quantity) AS ordered_qty,
           SUM(net_line) AS net_revenue,
           (1.0 * (SUM(returned_qty)) / NULLIF(SUM(quantity), 0)) AS return_rate
    FROM delivered_lines
    GROUP BY product_key
),
supplier_totals AS (
    SELECT s.supplier_id, s.supplier_name, s.is_preferred, s.rating_raw,
           CASE WHEN s.rating_raw > 5 THEN 10 WHEN s.rating_raw IS NOT NULL THEN 5 END
               AS rating_scale,
           COUNT(p.product_key) AS products,
           COUNT(t.product_key) AS products_sold,
           COALESCE(SUM(t.net_revenue), 0) AS net_revenue,
           SUM(CASE WHEN t.ordered_qty >= (SELECT CAST(value AS REAL) FROM run_params WHERE param = 'return_rate_min_volume') THEN 1 ELSE 0 END) AS products_rated,
           AVG(CASE WHEN t.ordered_qty >= (SELECT CAST(value AS REAL) FROM run_params WHERE param = 'return_rate_min_volume') THEN t.return_rate ELSE NULL END)
               AS avg_product_return_rate
    FROM dim_supplier AS s
    LEFT JOIN dim_product AS p ON p.supplier_key = s.supplier_key
    LEFT JOIN product_totals AS t ON t.product_key = p.product_key
    WHERE s.supplier_key <> -1
    GROUP BY s.supplier_key, s.supplier_id, s.supplier_name, s.is_preferred, s.rating_raw
),
scored AS (
    SELECT *,
           (1.0 * (net_revenue) / NULLIF(MAX(net_revenue) OVER (), 0)) AS revenue_score,
           1 - (1.0 * (avg_product_return_rate) / NULLIF(MAX(avg_product_return_rate) OVER (), 0))
               AS return_score,
           (1.0 * (rating_raw) / NULLIF(rating_scale, 0)) AS rating_score
    FROM supplier_totals
),
composite AS (
    SELECT *,
           (1.0 * (0.40 * COALESCE(revenue_score, 0)
               + 0.30 * COALESCE(return_score, 0)
               + 0.30 * COALESCE(rating_score, 0)) / NULLIF(0.40 * (revenue_score IS NOT NULL)
               + 0.30 * (return_score IS NOT NULL)
               + 0.30 * (rating_score IS NOT NULL), 0)) AS composite_score,
           (revenue_score IS NOT NULL) + (return_score IS NOT NULL)
               + (rating_score IS NOT NULL) AS components_used
    FROM scored
)
SELECT ROW_NUMBER() OVER (ORDER BY composite_score DESC, supplier_id) AS scorecard_rank,
       supplier_id,
       supplier_name,
       is_preferred,
       products,
       products_sold,
       products_rated,
       ROUND(net_revenue, 2) AS net_revenue,
       ROUND(100 * avg_product_return_rate, 2) AS avg_product_return_rate_pct,
       rating_raw,
       rating_scale,
       ROUND(revenue_score, 4) AS revenue_score,
       ROUND(return_score, 4) AS return_score,
       ROUND(rating_score, 4) AS rating_score,
       components_used,
       ROUND(composite_score, 4) AS composite_score
FROM composite
ORDER BY scorecard_rank;
