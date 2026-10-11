# Decisions and assumptions

| # | Topic | Decision | Why |
|---|---|---|---|
| 1 | Problem statement | `docs/Ecommerce_Analytics_Usecase.docx` is not in the repo; the pasted brief is the source of truth. | File missing. |
| 2 | Suppliers file | `suppliers_json.txt` renamed to `suppliers.json` at the owner's request (contents unchanged). | It is a JSON array. |
| 3 | Ambiguous slash dates | Parse per value: first part > 12 means DD/MM; second part > 12 means MM/DD; both <= 12 defaults to **MM/DD**. Such rows get `*_date_ambiguous = 1` (orders 63, payments 56, returns 9). | Both layouts occur in the same column. Among unambiguous orders, MM/DD (52) outnumbers DD/MM (43). Unconfirmed by the data owner. |
| 4 | Duplicate winner | Most complete cleansed record, then smallest content hash, then lowest source row. Losers go to quarantine (`DUPLICATE_EXACT` or `DUPLICATE_CONFLICT`). | No `last_updated` column. The hash step makes the result independent of file order. |
| 5 | Product list price <= 0 | Keep the product, set `unit_price` to NULL and `price_issue`. Not quarantined. | Revenue uses the line's own price; quarantining would orphan order lines. It also lets a complete duplicate win (P003, P060). |
| 6 | Order-line rules | Quarantine: quantity <= 0, negative or missing unit price, discount outside 0-100. | Revenue cannot be computed reliably. |
| 7 | `line_total` | Recomputed with Decimal `ROUND_HALF_UP`; source kept in `source_line_total`; `line_total_mismatch` if differing by > 0.01 (29 silver rows). | Source totals are often double or half the expected value. |
| 8 | Orphan foreign keys | Kept and flagged (`is_orphan_*`); in gold they point at the `-1` Unknown member. | Brief: do not drop. |
| 9 | Near-duplicate customers | Same normalised email **and** phone under different ids are flagged in `dup_group_id`, not merged. | Orders reference both ids; merging is irreversible. |
| 10 | Supplier rating scale | Detected from the file: smallest of 5/10/100 that contains the max rating. Found 10 (max 9.4). `rating_norm = rating / scale` (0-1). | Document-and-detect rather than assume. |
| 11 | Returned quantity | Refund >= line total: full line quantity (`FULL`). Otherwise `quantity * refund / line_total` (`PROPORTIONAL`). Missing refund or orphan item: NULL (`UNKNOWN`). `refund_exceeds_line` flags refunds above line value (4). | `returns.csv` has no quantity. |
| 12 | Return before order | 29 returns precede their order (26 unambiguous dates). Flagged `return_before_order`, kept. | A source defect; dropping would lose refunds. |
| 13 | Date outliers | 6 orders dated 2020-2022 and 2 signups in 2027 are kept as stated. | Dates are valid; cause unknown. |
| 14 | Reference date | Latest order date in silver, never today. Stored in `run_params`. | Brief. |
| 15 | `_loaded_at` | Real load time, so it differs per run; idempotency comparisons exclude it. | Lineage needs a true timestamp. |
| 16 | Commits | No commits are made by the assistant. | Owner preference. |
