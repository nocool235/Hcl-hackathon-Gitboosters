# KPI report

Run on BigQuery dataset `gitbooster.shopsphere_gold` (gold last loaded 2026-10-11 09:49 UTC).
Parameters: `return_rate_min_volume` = 10, `payment_tolerance` = 1.0, `repeat_window_days` = 90, `reference_date` = None (`reference_date` None = latest order date).

Each section's definition, inclusions and exclusions come from the comment header of its SQL file. Regenerate with `python -m hackathon.kpis`.

## KPI 1: Net revenue by product category per month

SQL: [kpi_01_net_revenue_category_month.sql](../kpis/bigquery/kpi_01_net_revenue_category_month.sql) · Output: [kpi_01_net_revenue_category_month.csv](../outputs/kpis/kpi_01_net_revenue_category_month.csv) · Rows: 123

- **Definition:** net revenue per order month (YYYY-MM of the order date) and standardised product category.
- **Measure:** net revenue = recomputed line revenue after discount (fact_order_items.line_total) - approved refunds. Each refund is capped at its line_total, so a line never goes below zero.
- **Data quality:** resolved in silver before this KPI: duplicate and conflicting product records (one winner per product_id, the losers quarantined); category labels standardised (e.g. 'electornics' -> Electronics, 'homeandkitchen' -> Home & Kitchen); a blank category on 5 products (P008, P017, P054, P059, P066) filled from their sub-category, which maps to exactly one category across all other products (flagged in dim_product.category_inferred); line_total recomputed from quantity, unit price and discount because 29 source totals were wrong; order dates in mixed formats parsed (63 slash dates with both parts <= 12 read as MM/DD and flagged, which can move an order between months); lines with quantity <= 0, a missing or negative price, or a discount outside 0-100 quarantined. Handled here: refunds above their line value are capped.
- **Inclusions:** lines on orders with status Completed or Returned. Lines for products missing from the product file are kept under category 'Unknown' (after the category fill, these are the only Unknown lines).
- **Exclusions:** Cancelled and Pending orders (and refunds on their lines, since their revenue is never counted); lines whose order is missing from fact_orders (status unknown); refunds with return_status Pending or Rejected or no amount; returns whose order item is unknown.
- **Returned orders:** kept at full line revenue, and their approved refunds are subtracted once, line by line. Order status is never used to remove revenue, so a refund cannot be subtracted twice. A Returned order with no approved refund keeps its full revenue.
- **Refund timing:** refunds are attributed to the original order month, not the return month.
- **Alternatives:** (1) attribute refunds to the return_date month (cash view); that moves refunds into later months and puts the 29 returns dated before their order in a month earlier than the sale. (2) Count Completed orders only, dropping Returned orders and their refunds; this lowers revenue and hides refund activity.
- **Assumptions:** source_line_total is ignored. Payment rows with status Refunded are not used: fact_returns is the single refund source, and using both would double count.

**Result (first 10 of 123 rows)**

| order_month | category | orders | order_lines | gross_revenue | refunds | net_revenue |
|---|---|---|---|---|---|---|
| 2020-10 | Grocery | 1 | 1 | 45144.5 | 0 | 45144.5 |
| 2020-12 | Home & Kitchen | 1 | 1 | 21122.18 | 0 | 21122.18 |
| 2021-09 | Grocery | 1 | 1 | 13037.07 | 0 | 13037.07 |
| 2021-09 | Home & Kitchen | 1 | 1 | 56241.65 | 0 | 56241.65 |
| 2021-12 | Electronics | 1 | 1 | 16084.14 | 0 | 16084.14 |
| 2021-12 | Grocery | 1 | 1 | 88376.9 | 0 | 88376.9 |
| 2022-05 | Fashion | 1 | 1 | 9607.25 | 0 | 9607.25 |
| 2022-05 | Grocery | 1 | 1 | 17582.77 | 0 | 17582.77 |
| 2022-05 | Sports | 1 | 1 | 81924.16 | 0 | 81924.16 |
| 2024-01 | Electronics | 3 | 3 | 152376.05 | 0 | 152376.05 |

## KPI 2: Top 10 customers by net lifetime value

SQL: [kpi_02_top_customers_net_ltv.sql](../kpis/bigquery/kpi_02_top_customers_net_ltv.sql) · Output: [kpi_02_top_customers_net_ltv.csv](../outputs/kpis/kpi_02_top_customers_net_ltv.csv) · Rows: 10

- **Definition:** the 10 customers with the highest net lifetime value (LTV) from completed orders.
- **Measure:** net LTV = SUM(line_total) - approved refunds (each capped at its line_total) over the customer's completed orders (order_status = 'Completed').
- **Ranking:** net LTV descending, then completed order count descending, then customer_key ascending.
- **Data quality:** resolved in silver before this KPI: exact duplicate customer rows removed; order status labels standardised (e.g. 'complted' -> Completed); line_total recomputed. Orphaned references (orders whose customer id is not in the customer file, customer_key = -1) and ambiguous references (near-duplicate customers: same normalised email and phone under different ids, dup_group_id set) are kept and flagged in gold, not dropped.
- **Orphaned and ambiguous references:** decision: kept out of the ranking and reported with their count and value in kpi_02b_customer_reference_exceptions, so a customer is never ranked on a guessed identity.
- **Inclusions:** customers present in dim_customer with no near-duplicate flag.
- **Exclusions:** Cancelled, Pending and Returned orders; refunds with return_status Pending or Rejected or no amount; completed orders with no valid lines.
- **Alternatives:** (1) merge each near-duplicate group into one customer and rank it (irreversible, and the source gives no proof they are the same person). (2) rank orphaned ids as their own customers by source id (no name or segment is known for them). (3) include Returned orders net of their refunds.
- **Assumptions:** one dim_customer version per customer today, so customer_key identifies a customer.

**Result (first 10 of 10 rows)**

| ltv_rank | customer_id | customer_key | customer_name | customer_segment | completed_orders | net_lifetime_value |
|---|---|---|---|---|---|---|
| 1 | C0118 | 260888476431569 | Utkarsh Bhat | Gold | 3 | 532447.01 |
| 2 | C0107 | 168312992229569 | Eesha Sethi | Silver | 2 | 463604.51 |
| 3 | C0061 | 204054093418395 | Yadavi Bhakta | Platinum | 2 | 341730.61 |
| 4 | C0148 | 206460803151188 | Ucchal Thaker | Bronze | 3 | 329199.64 |
| 5 | C0142 | 63843893294064 | Zansi Prasad | Platinum | 4 | 328510.37 |
| 6 | C0001 | 129200680737809 | Isaac Bakshi | Bronze | 4 | 302064 |
| 7 | C0085 | 173802208651783 | Chakrika Koshy | Silver | 3 | 291047.36 |
| 8 | C0033 | 100961223590592 | Hamsini Rao | Gold | 2 | 268013.97 |
| 9 | C0129 | 179502427755416 | Siddharth Bains | Platinum | 3 | 265776.18 |
| 10 | C0037 | 52655520243140 | Gautam Rana | Gold | 2 | 259380.42 |

## KPI 2 (companion): Customer references excluded from the ranking

SQL: [kpi_02b_customer_reference_exceptions.sql](../kpis/bigquery/kpi_02b_customer_reference_exceptions.sql) · Output: [kpi_02b_customer_reference_exceptions.csv](../outputs/kpis/kpi_02b_customer_reference_exceptions.csv) · Rows: 2

- **Definition:** completed-order value that KPI 2 keeps out of its ranking, with counts, so it is reported, not lost. Part of KPI 2, not a separate KPI.
- **Measure:** same net value as KPI 2 (line_total - approved refunds, capped per line), completed orders only.
- **ORPHAN_CUSTOMER:** orders whose customer id is not in the customer file (customer_key = -1). customer_references = distinct unmatched source customer ids.
- **AMBIGUOUS_CUSTOMER:** orders from near-duplicate customers (same normalised email and phone under different ids, dup_group_id set). customer_references = distinct customer ids; dup_groups = distinct duplicate groups.
- **Exclusions:** Cancelled, Pending and Returned orders; refunds with return_status Pending or Rejected or no amount; completed orders with no valid lines.
- **Assumptions:** both rows are always returned (zeros when there are no exceptions).

**Result (first 2 of 2 rows)**

| reference_type | customer_references | dup_groups | completed_orders | net_value |
|---|---|---|---|---|
| ORPHAN_CUSTOMER | 7 | 0 | 7 | 542685.66 |
| AMBIGUOUS_CUSTOMER | 2 | 1 | 2 | 44528.53 |

## KPI 3: Standardised customer segment profile

SQL: [kpi_03_customer_segment_profile.sql](../kpis/bigquery/kpi_03_customer_segment_profile.sql) · Output: [kpi_03_customer_segment_profile.csv](../outputs/kpis/kpi_03_customer_segment_profile.csv) · Rows: 5

- **Definition:** per standardised customer segment, the number of customers and the average order value (AOV).
- **Measure:** AOV = net order value / distinct completed orders. Net order value = SUM(fact_order_items.line_total) - approved refunds (each refund capped at its line_total).
- **Numerator:** net order value of completed orders placed by customers in the segment.
- **Denominator:** distinct completed orders (order_status = 'Completed') that have at least one valid order line.
- **Data quality:** resolved in silver before this KPI: customer_segment standardised from mixed spelling and casing (e.g. 'glod' -> Gold, 'silverr' -> Silver, 'broze' / 'BRONZE' -> Bronze; blank -> Unknown); exact duplicate customer rows removed; order status labels standardised; line_total recomputed. Orders from customer ids missing from the customer file are kept under segment 'Unknown' (customer_count 0, buying_customers = distinct unmatched ids) so the segment totals still add up to all completed orders.
- **Inclusions:** customer_count counts every customer in dim_customer, whether or not they ordered. buying_customers counts distinct customer ids with at least one completed order.
- **Exclusions:** Cancelled, Pending and Returned orders; refunds with return_status Pending or Rejected or no amount; completed orders with no valid lines (all lines quarantined, value unknown).
- **Alternatives:** (1) gross AOV, before refunds (higher in every segment). (2) average per customer instead of per order (net value / buying customers). (3) customer_count of buying customers only.
- **Assumptions:** near-duplicate customers (same email and phone, dup_group_id) are counted separately, not merged. dim_customer has one version per customer today, so the segment is the current one.

**Result (first 5 of 5 rows)**

| customer_segment | customer_count | buying_customers | completed_orders | net_order_value | avg_order_value |
|---|---|---|---|---|---|
| Platinum | 44 | 30 | 51 | 3928955.42 | 77038.34 |
| Gold | 38 | 20 | 32 | 3008607.31 | 94018.98 |
| Silver | 40 | 25 | 36 | 3047876.88 | 84663.25 |
| Bronze | 36 | 22 | 36 | 2522683.34 | 70074.54 |
| Unknown | 0 | 7 | 7 | 542685.66 | 77526.52 |

## KPI 4: Month-over-month order volume and net revenue growth by channel

SQL: [kpi_04_channel_mom_growth.sql](../kpis/bigquery/kpi_04_channel_mom_growth.sql) · Output: [kpi_04_channel_mom_growth.csv](../outputs/kpis/kpi_04_channel_mom_growth.csv) · Rows: 189

- **Definition:** per channel and calendar month, order count and net revenue, with growth versus the previous month.
- **Measure:** growth_pct = 100 \* (this month - previous month) / previous month, previous month taken with the LAG() window function.
- **Calendar:** every month from the first to the last month with an in-scope order, for every channel, so months with no orders appear as 0 and LAG() always compares adjacent months.
- **Growth rules:** previous month 0 -> growth NULL, flag PRIOR_MONTH_ZERO. Previous net revenue below 0 -> growth NULL, flag PRIOR_MONTH_NEGATIVE. First month of the calendar -> growth NULL, flag FIRST_MONTH.
- **Data quality:** resolved in silver before this KPI: channel labels standardised to Web / App / Store (e.g. 'web', 'APP', 'instore' -> Store); order status labels standardised; order dates in mixed formats parsed (63 ambiguous slash dates read as MM/DD and flagged, which can move an order between months); line_total recomputed. 6 orders dated 2020-2022 are valid dates kept as stated (cause unknown).
- **Inclusions:** orders with status Completed or Returned (same scope as KPI 1). Orders with no valid lines count toward volume with 0 revenue.
- **Exclusions:** Cancelled and Pending orders; refunds with return_status Pending or Rejected or no amount.
- **Alternatives:** (1) compare only months that have orders (skipping empty months) - rejected, because growth would then compare non-adjacent months. (2) Completed orders only. (3) gross revenue before refunds.
- **Assumptions:** net revenue = line_total - approved refunds (capped per line), refunds in the order month. Because of the 2020-2022 orders the calendar starts in 2020-10; filter by month for 2024-2025 trading.

**Result (first 10 of 189 rows)**

| channel | order_month | order_count | prev_order_count | order_growth_pct | order_growth_flag | net_revenue | prev_net_revenue | revenue_growth_pct | revenue_growth_flag |
|---|---|---|---|---|---|---|---|---|---|
| App | 2020-10 | 0 |  |  | FIRST_MONTH | 0 |  |  | FIRST_MONTH |
| App | 2020-11 | 0 | 0 |  | PRIOR_MONTH_ZERO | 0 | 0 |  | PRIOR_MONTH_ZERO |
| App | 2020-12 | 1 | 0 |  | PRIOR_MONTH_ZERO | 21122.18 | 0 |  | PRIOR_MONTH_ZERO |
| App | 2021-01 | 0 | 1 | -100.0 |  | 0 | 21122.18 | -100 |  |
| App | 2021-02 | 0 | 0 |  | PRIOR_MONTH_ZERO | 0 | 0 |  | PRIOR_MONTH_ZERO |
| App | 2021-03 | 0 | 0 |  | PRIOR_MONTH_ZERO | 0 | 0 |  | PRIOR_MONTH_ZERO |
| App | 2021-04 | 0 | 0 |  | PRIOR_MONTH_ZERO | 0 | 0 |  | PRIOR_MONTH_ZERO |
| App | 2021-05 | 0 | 0 |  | PRIOR_MONTH_ZERO | 0 | 0 |  | PRIOR_MONTH_ZERO |
| App | 2021-06 | 0 | 0 |  | PRIOR_MONTH_ZERO | 0 | 0 |  | PRIOR_MONTH_ZERO |
| App | 2021-07 | 0 | 0 |  | PRIOR_MONTH_ZERO | 0 | 0 |  | PRIOR_MONTH_ZERO |

## KPI 5: Product return rate (top 10 and bottom 10)

SQL: [kpi_05_product_return_rate.sql](../kpis/bigquery/kpi_05_product_return_rate.sql) · Output: [kpi_05_product_return_rate.csv](../outputs/kpis/kpi_05_product_return_rate.csv) · Rows: 20

- **Definition:** return rate per product = returned quantity / ordered quantity.
- **Numerator:** returned quantity of returns not Rejected (Approved or Pending), on lines in the denominator.
- **Denominator:** ordered quantity on lines of Completed or Returned orders (goods that reached the customer).
- **Threshold:** only products with ordered quantity >= @return_rate_min_volume (config medallion.return_rate_min_volume) are ranked, so low-sales products do not distort the ranking.
- **Data quality:** returns.csv has no quantity column, so the pipeline derives it: the full line quantity when the refund covers the line value (FULL), otherwise quantity \* refund / line value (PROPORTIONAL, can be fractional); returns with no refund amount get an unknown quantity (counted in returns_unknown_qty, adding 0). Also resolved in silver: duplicate return rows removed; return status labels standardised; duplicate and conflicting product records resolved. 29 returns dated before their order are kept (dates do not affect a rate). Returns whose order item is unknown cannot be tied to a product and are excluded.
- **Output:** ranking TOP = highest return rate, BOTTOM = lowest. Ties: higher ordered quantity first, then product_id. A product can appear in both lists when fewer than 20 products qualify (see products_qualifying).
- **Exclusions:** Cancelled and Pending orders; Rejected returns; lines for products missing from the product file (product_key = -1).
- **Alternatives:** (1) Approved returns only (stricter; a Pending return is still goods coming back). (2) count-based rate: returned lines / ordered lines. (3) all order statuses in the denominator (counts goods never shipped).

**Result (first 10 of 20 rows)**

| ranking | rank_in_list | product_id | product_name | category | ordered_qty | returned_qty | return_rate_pct | returns | returns_unknown_qty | products_qualifying |
|---|---|---|---|---|---|---|---|---|---|---|
| TOP | 1 | P018 | Team Sports Item 18 | Sports | 14 | 4.9236 | 35.17 | 1 | 0 | 65 |
| TOP | 2 | P045 | Footwear Item 45 | Fashion | 13 | 3.4739 | 26.72 | 1 | 0 | 65 |
| TOP | 3 | P057 | Team Sports Item 57 | Sports | 28 | 7.2089 | 25.75 | 2 | 0 | 65 |
| TOP | 4 | P069 | Mobiles Item 69 | Electronics | 12 | 2.5947 | 21.62 | 1 | 0 | 65 |
| TOP | 5 | P034 | Fitness Item 34 | Sports | 25 | 5.3203 | 21.28 | 2 | 0 | 65 |
| TOP | 6 | P029 | Furniture Item 29 | Home & Kitchen | 28 | 5.7426 | 20.51 | 2 | 0 | 65 |
| TOP | 7 | P052 | Womenswear Item 52 | Fashion | 24 | 4.2061 | 17.53 | 1 | 0 | 65 |
| TOP | 8 | P067 | Appliances Item 67 | Home & Kitchen | 20 | 3.4464 | 17.23 | 1 | 0 | 65 |
| TOP | 9 | P040 | Footwear Item 40 | Fashion | 31 | 4.8326 | 15.59 | 1 | 0 | 65 |
| TOP | 10 | P009 | Furniture Item 9 | Home & Kitchen | 23 | 3.3303 | 14.48 | 1 | 0 | 65 |

## KPI 6: Supplier performance scorecard

SQL: [kpi_06_supplier_scorecard.sql](../kpis/bigquery/kpi_06_supplier_scorecard.sql) · Output: [kpi_06_supplier_scorecard.csv](../outputs/kpis/kpi_06_supplier_scorecard.csv) · Rows: 18

- **Definition:** per supplier, net revenue from its products, the average return rate of its products and its quality rating normalised to 0-1, combined into a 0-1 composite score and ranked.
- **Data quality:** ratings were entered on an inconsistent scale: 15 suppliers are rated 1.6-5.0 and 3 are rated 7.5-9.4, i.e. some out of 5 and some out of 10. Each rating is normalised on its own scale here: rating > 5 -> out of 10, otherwise out of 5 (rating_scale). The pipeline's rating_norm divides every rating by 10, which would halve every 5-point rating, so it is not used. Also resolved in silver: conflicting duplicate supplier rows (S004 under two names, one quarantined); duplicate and conflicting product records.
- **Measures:** net_revenue = line_total - approved refunds (capped per line) on Completed or Returned orders, for the supplier's products (same scope as KPI 1). avg_product_return_rate = unweighted average of the KPI 5 return rate over the supplier's products that meet @return_rate_min_volume (config); products_rated shows how many products that is.
- **Composite weighting:** 0.40 revenue + 0.30 returns + 0.30 rating, each component scaled 0-1: revenue_score = net_revenue / highest supplier net_revenue; return_score = 1 - avg_product_return_rate / highest supplier average (fewer returns scores higher); rating_score = rating / rating_scale. A missing component (no product meets the volume threshold, or no rating) is left out and the remaining weights are rescaled to sum to 1; components_used shows how many were used.
- **Ranking:** composite_score descending, then supplier_id.
- **Exclusions:** products whose supplier is missing from the supplier file (supplier_key = -1) and order lines for unknown products; Cancelled and Pending orders; Rejected returns in the return rate.
- **Alternatives:** (1) one scale for every supplier (all out of 10), which halves the 5-point ratings. (2) other weights, e.g. 0.50 / 0.30 / 0.20. (3) revenue as share of total revenue (then revenue barely moves the score unless rescaled). (4) a 10-point supplier rated 5 or below would be misread as out of 5; the data gives no way to tell, so this is the interim assumption.

**Result (first 10 of 18 rows)**

| scorecard_rank | supplier_id | supplier_name | is_preferred | products | products_sold | products_rated | net_revenue | avg_product_return_rate_pct | rating_raw | rating_scale | revenue_score | return_score | rating_score | components_used | composite_score |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | S007 | Biswas, Karpe and Radhakrishnan | False | 6 | 6 | 6 | 1839381.73 | 0 | 4.2 | 5 | 0.8392 | 1 | 0.84 | 3 | 0.8877 |
| 2 | S006 | Lalla, Ganesh and Oommen | False | 9 | 8 | 7 | 2191898.43 | 4.1 | 7.5 | 10 | 1 | 0.8073 | 0.75 | 3 | 0.8672 |
| 3 | S015 | Chaudhari, Sandal and Desai | False | 4 | 4 | 4 | 1821770.44 | 1.88 | 4.1 | 5 | 0.8311 | 0.9116 | 0.82 | 3 | 0.8519 |
| 4 | S004 | Sinha, Subramaniam and Garde | True | 4 | 4 | 4 | 1612831.39 | 5.8 | 9.4 | 10 | 0.7358 | 0.7274 | 0.94 | 3 | 0.7945 |
| 5 | S005 | Dhar-Gopal | True | 2 | 2 | 1 | 830441.17 | 0 | 4.5 | 5 | 0.3789 | 1 | 0.9 | 3 | 0.7215 |
| 6 | S001 | Baral, Din and Bhalla | False | 3 | 3 | 3 | 1283272.11 | 6.74 | 4.3 | 5 | 0.5855 | 0.6831 | 0.86 | 3 | 0.6971 |
| 7 | S018 | Amble, Virk and Dalal | False | 4 | 4 | 4 | 615765.99 | 1.89 | 5 | 5 | 0.2809 | 0.9111 | 1 | 3 | 0.6857 |
| 8 | S009 | Saini, Doctor and Char | False | 2 | 2 | 2 | 657783.34 | 0 | 4 | 5 | 0.3001 | 1 | 0.8 | 3 | 0.66 |
| 9 | S014 | Raj-Palla | True | 5 | 5 | 5 | 1166889.05 | 1.82 | 2.5 | 5 | 0.5324 | 0.9145 | 0.5 | 3 | 0.6373 |
| 10 | S008 | Babu and Sons | False | 2 | 2 | 2 | 611245.71 | 0 | 3.7 | 5 | 0.2789 | 1 | 0.74 | 3 | 0.6335 |

## KPI 7: Repeat-purchase rate

SQL: [kpi_07_repeat_purchase_rate.sql](../kpis/bigquery/kpi_07_repeat_purchase_rate.sql) · Output: [kpi_07_repeat_purchase_rate.csv](../outputs/kpis/kpi_07_repeat_purchase_rate.csv) · Rows: 2

- **Definition:** share of customers who place another completed order within @repeat_window_days (config, 90) of their first completed order.
- **Numerator:** customers with at least one other completed order dated from their first order date up to first order date + window (a second order on the same day counts).
- **Denominator:** customers with at least one completed order (order_status = 'Completed').
- **Primary:** FULL_WINDOW, restricted to customers whose first order date + window <= reference date, so every customer has had the full window to repeat. ALL_CUSTOMERS includes recent first-time customers who have not had 90 days yet, which pulls the rate down; it is reported for comparison.
- **Data quality:** resolved in silver before this KPI: order status labels standardised; order dates in mixed formats parsed (63 ambiguous slash dates read as MM/DD and flagged; a misread date can move an order in or out of the 90-day window); exact duplicate orders removed, so a duplicated order is never counted as a repeat. Orders whose customer id is missing from the customer file (customer_key = -1) cannot be linked into a purchase history and are excluded. Near-duplicate customers are counted separately (not merged).
- **Exclusions:** Cancelled, Pending and Returned orders.
- **Alternatives:** (1) ALL_CUSTOMERS as the headline (simpler, but biased down by customers still inside their window). (2) count Returned orders as purchases. (3) require the repeat order strictly after the first day.
- **Assumptions:** reference date = @reference_date (config medallion.reference_date); when null, the latest order date in fact_orders (never today). First order = earliest order_date, ties broken by order_id.

**Result (first 2 of 2 rows)**

| cohort | is_primary | customers_denominator | repeat_customers | repeat_rate_pct | window_days | reference_date |
|---|---|---|---|---|---|---|
| FULL_WINDOW | True | 92 | 8 | 8.7 | 90 | 2025-12-05 |
| ALL_CUSTOMERS | False | 98 | 8 | 8.16 | 90 | 2025-12-05 |

## KPI 8: Payment reconciliation per order

SQL: [kpi_08_payment_reconciliation.sql](../kpis/bigquery/kpi_08_payment_reconciliation.sql) · Output: [kpi_08_payment_reconciliation.csv](../outputs/kpis/kpi_08_payment_reconciliation.csv) · Rows: 328

- **Definition:** for each order, successful payments compared with the computed order total, with anomaly flags.
- **Measure:** difference = paid_amount - order_total, where paid_amount = SUM(amount) of payment_status 'Success' and order_total = SUM(fact_order_items.line_total) (recomputed lines, before refunds).
- **Status (first match wins):** ORPHAN_PAYMENT (payments for an order id missing from fact_orders); NO_SUCCESSFUL_PAYMENT; NO_VALID_LINES (order has no valid lines, total unknown); UNDERPAID (paid < total - tolerance); OVERPAID (paid > total + tolerance); else MATCHED. tolerance = @payment_tolerance (config medallion.payment_tolerance).
- **Flags:** duplicate_payment = a payment row recorded twice: an exact duplicate removed in silver (quarantined_duplicate_rows, from quarantine_payments) or two Success rows with the same amount in gold. conflicting_payments = more than one payment row with different amounts or statuses, or a conflicting duplicate quarantined in silver (quarantined_conflicting_rows).
- **Data quality:** resolved in silver before this KPI: payment amounts in mixed formats (e.g. '₹210,054.96', '73078.38 INR') parsed to numbers; payment status labels standardised (e.g. 'SUCCESS', 'Succeded' -> Success); exact duplicate payment rows removed and quarantined (counted back here, so they are flagged rather than lost); order totals use recomputed line_total. Payments whose order is missing are kept.
- **Double counting:** payments, order lines and quarantined rows are each aggregated to one row per order before they are joined.
- **Inclusions:** every order whatever its status (order_status is shown, so filter to Completed to reconcile recognised revenue), plus orphan payments.
- **Exclusions:** Failed, Pending and Refunded payments do not count toward paid_amount (they are still counted in payment_rows).
- **Alternatives:** (1) compare with the order total net of approved refunds. (2) count Pending payments as paid. (3) a different tolerance (config).
- **Order:** exceptions first, then MATCHED, each by order_id.

**Result (first 10 of 328 rows)**

| order_id | order_status | line_count | order_total | payment_rows | success_rows | paid_amount | difference | reconciliation_status | quarantined_duplicate_rows | quarantined_conflicting_rows | duplicate_payment | conflicting_payments |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| O00002 | Cancelled | 1 | 21724.64 | 1 | 0 | 0 | -21724.64 | NO_SUCCESSFUL_PAYMENT | 0 | 0 | False | False |
| O00003 | Completed | 1 | 33974.88 | 1 | 0 | 0 | -33974.88 | NO_SUCCESSFUL_PAYMENT | 0 | 0 | False | False |
| O00009 | Completed | 2 | 40778.86 | 1 | 0 | 0 | -40778.86 | NO_SUCCESSFUL_PAYMENT | 0 | 0 | False | False |
| O00012 | Completed | 4 | 141177.62 | 1 | 0 | 0 | -141177.62 | NO_SUCCESSFUL_PAYMENT | 0 | 0 | False | False |
| O00013 | Completed | 2 | 25431.4 | 1 | 0 | 0 | -25431.4 | NO_SUCCESSFUL_PAYMENT | 0 | 0 | False | False |
| O00016 | Cancelled | 1 | 80420.7 | 1 | 0 | 0 | -80420.7 | NO_SUCCESSFUL_PAYMENT | 0 | 0 | False | False |
| O00017 | Completed | 1 | 27430.41 | 0 | 0 | 0 | -27430.41 | NO_SUCCESSFUL_PAYMENT | 0 | 0 | False | False |
| O00019 | Pending | 2 | 140291.34 | 0 | 0 | 0 | -140291.34 | NO_SUCCESSFUL_PAYMENT | 0 | 0 | False | False |
| O00021 | Pending | 1 | 29190.88 | 1 | 0 | 0 | -29190.88 | NO_SUCCESSFUL_PAYMENT | 0 | 0 | False | False |
| O00023 | Completed | 2 | 22602.06 | 1 | 0 | 0 | -22602.06 | NO_SUCCESSFUL_PAYMENT | 0 | 0 | False | False |

## Stretch: Margin risk report

SQL: [stretch_margin_risk.sql](../kpis/bigquery/stretch_margin_risk.sql) · Output: [stretch_margin_risk.csv](../outputs/kpis/stretch_margin_risk.csv) · Rows: 26

- **Definition:** products sold at a loss, i.e. order lines where the product's cost_price exceeds the effective selling price per unit after discount.
- **Measure:** effective selling price = line_total / quantity (recomputed line value after discount). affected_quantity and affected_revenue (quantity and revenue exposed) sum the lines sold below cost. margin_shortfall = SUM(cost_price \* quantity - line_total) over those lines (the loss versus cost).
- **Data quality:** resolved in silver before this report: duplicate and conflicting product records (one cost per product); line_total recomputed from quantity, unit price and discount; order lines with an invalid quantity, price or discount quarantined. Products whose list price is invalid (price_issue) keep a NULL list price; the line's own price is used here, so they are still checked.
- **Inclusions:** lines on Completed or Returned orders (same revenue scope as KPI 1).
- **Exclusions:** Cancelled and Pending orders; products missing from the product file (product_key = -1); products without a cost_price.
- **Alternatives:** (1) compare cost with the product list price after discount instead of the line's own price. (2) include Cancelled and Pending orders (counts sales that did not happen). (3) subtract refunds.
- **Assumptions:** refunds are not subtracted (this is a pricing check on the sale, not net revenue). cost_price is the current product cost from dim_product; there is no cost history.

**Result (first 10 of 26 rows)**

| product_id | product_name | category | cost_price | min_net_unit_price | max_net_unit_price | affected_lines | affected_quantity | affected_revenue | margin_shortfall |
|---|---|---|---|---|---|---|---|---|---|
| P065 | Footwear Item 65 | Fashion | 23290.69 | 12564.83 | 15706.03 | 14 | 44 | 637664.84 | 387125.52 |
| P013 | Appliances Item 13 | Home & Kitchen | 24940.49 | 12498.15 | 15622.68 | 9 | 22 | 308547.93 | 240142.85 |
| P060 | Staples Item 60 (Revised) | Grocery | 18576.25 | 9834.14 | 11569.57 | 7 | 24 | 257422.94 | 188407.06 |
| P039 | Fitness Item 39 | Sports | 14577.41 | 4654.91 | 5818.64 | 5 | 19 | 99789.68 | 177181.11 |
| P001 | Accessories Item 1 | Electronics | 16799.61 | 10127.75 | 10660.79 | 5 | 13 | 134858.99 | 83535.94 |
| P028 | Appliances Item 28 | Home & Kitchen | 9457.58 | 5774.82 | 7218.53 | 7 | 19 | 125241.49 | 54452.53 |
| P020 | Beverages Item 20 | Grocery | 5171.78 | 2907.66 | 3634.57 | 8 | 25 | 83231.65 | 46062.85 |
| P006 | Furniture Item 6 | Home & Kitchen | 4549.93 | 2433.63 | 2863.09 | 4 | 11 | 30205.6 | 19843.63 |
| P051 | Footwear Item 51 | Fashion | 4574.85 | 701.19 | 3446.09 | 3 | 6 | 8336.15 | 19112.95 |
| P002 | Furniture Item 2 | Home & Kitchen | 9027.17 | 7962.87 | 8958.23 | 5 | 22 | 180159.99 | 18437.75 |
