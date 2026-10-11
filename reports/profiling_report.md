# ShopSphere — Phase 1 Profiling Report

> Generated: 2026-10-11  
> Source path: `data/raw/Ecommerce_Analytics_SourceData/Ecommerce_Analytics_SourceData/`  
> All files are **read-only**; no source file has been modified.

---

## 1. File inventory

| File | Format | Rows | Columns | Notes |
|------|--------|------|---------|-------|
| `customers.csv` | CSV | 163 | 13 | — |
| `orders.csv` | CSV | 323 | 8 | — |
| `order_items.csv` | CSV | 802 | 7 | — |
| `payments.csv` | CSV | 329 | 6 | — |
| `products.csv` | CSV | 75 | 9 | — |
| `returns.csv` | CSV | 68 | 6 | — |
| `suppliers_json.txt` | JSON (array) | 19 | 6 | **Not** `.json` extension — treated as JSON |

---

## 2. Column-level profiles

### 2.1 customers.csv

| Column | Nulls/Blank | Distinct | Key findings |
|--------|-------------|----------|--------------|
| customer_id | 0 | 158 (163 rows) | 5 conflicting duplicates |
| first_name | 0 | 149 | OK |
| last_name | 0 | 151 | OK |
| email | **6 null** | 157 | Case variants used as duplicates; 18 rows share 6 distinct email values |
| phone | **2 null** | 142 | 3 formats: local 10-digit, `+91-…`, `(NNN) NNN-NNNN` |
| address_line1 | 0 | 163 | OK |
| city | 0 | 27 | Casing variants (BANGALORE, Bangalore) |
| state | 0 | 20 | OK |
| zip_code | **4 null/N-A** | 152 | Some "N/A" values (pandas reads as null) |
| country | 0 | 1 | All "India" |
| signup_date | **3 null** | 157 | 3 formats: `YYYY-MM-DD` (41), `DD/MM` or `MM/DD` slash (86), `DD-Mon-YYYY` (32) — **ambiguous slash; see §3** |
| customer_segment | 0 | 15 | Typos: "Glod", "Silverr", "Broze"; casing variants |
| is_active | 0 | 8 | Variants: Y / yes / true / True / 1 / N / False / 0 / no |

### 2.2 orders.csv

| Column | Nulls/Blank | Distinct | Key findings |
|--------|-------------|----------|--------------|
| order_id | 0 | 320 (323 rows) | 3 exact duplicate order rows (6 rows) |
| customer_id | 0 | 310 | 15 orphan customer IDs (format `C9XXX` — no match in customers) |
| order_date | 0 | 280 | 3 formats: `MM/DD or DD/MM slash` (163), `DD-Mon-YYYY` (84), `YYYY-MM-DD` (76) — **mixed slash; see §3** |
| order_status | 0 | 13 | Typos: "Complted", "Cancled"; casing; "COMPLETE"; "Canceled"/"Cancelled" |
| payment_method | 0 | 5 | OK |
| channel | 0 | 10 | Variants: web/Web/WEB/app/App/APP/store/Store/In-store/Instore |
| promo_code | **228 "NA"→null** | 22 | pandas reads "NA" as null; these mean no promo used |
| shipping_city | 0 | 27 | Casing variants |

### 2.3 order_items.csv

| Column | Nulls/Blank | Distinct | Key findings |
|--------|-------------|----------|--------------|
| order_item_id | 0 | 797 (802 rows) | 5 exact duplicate rows (10 rows) |
| order_id | 0 | 314 | 10 orphan order IDs (format `O9XXXX`) |
| product_id | 0 | 72 | 8 orphan product IDs (format `P9XX`) |
| quantity | 0 | 10 | **10 non-positive values** (6 zero, 4 negative) |
| unit_price | **5 null** | 67 | **10 rows with negative price** (all P003 at -70.38; see conflicting product dup) |
| discount_pct | 0 | 11 | **7 rows outside 0–100**: includes -10 and 150 |
| line_total | 0 | 706 | **51 mismatches** vs `ROUND(qty × price × (1 - disc/100), 2)` |

### 2.4 payments.csv

| Column | Nulls/Blank | Distinct | Key findings |
|--------|-------------|----------|--------------|
| payment_id | 0 | 325 (329 rows) | 4 exact duplicate rows (8 rows) |
| order_id | 0 | 321 | 8 orphan order IDs (format `O9XXXX`) |
| payment_date | **10 null** | 312 | 3 formats same as order_date; **mixed slash** |
| amount | 0 | 322 | **94 rows prefixed with `₹` and comma-formatted** (e.g. `₹210,054.96`) |
| payment_status | 0 | 11 | Variants: Success/SUCCESS/success/**Succeded** (typo)/Pending/FAILED/Failed/Refunded |
| payment_method | 0 | 5 | OK |

### 2.5 products.csv

| Column | Nulls/Blank | Distinct | Key findings |
|--------|-------------|----------|--------------|
| product_id | 0 | 70 (75 rows) | **5 conflicting duplicate product IDs** |
| product_name | **2 null** | 72 | P059, P008 have no name |
| category | **5 null** | 14 | Typo "Electornics"; casing; "Home and Kitchen" vs "Home & Kitchen" |
| sub_category | 0 | 13 | OK |
| unit_price | 0 | 69 | **4 non-positive**: P003 (−70.38), P040/P051/P060 (0); P070 has `₹2,902.33` format |
| cost_price | 0 | 69 | 14 rows where `cost_price > unit_price` (margin risk) |
| supplier_id | 0 | 23 | **4 orphan supplier IDs** (S92, S93, S96, S98 — different ID format) |
| is_active | 0 | 9 | Same boolean variants as customers |
| launch_date | 0 | 70 | 3 date formats |

### 2.6 returns.csv

| Column | Nulls/Blank | Distinct | Key findings |
|--------|-------------|----------|--------------|
| return_id | 0 | 65 (68 rows) | 3 exact duplicate return rows (6 rows) |
| order_item_id | 0 | 62 | **6 orphan order_item_ids** (format `OI9XXXXX`) |
| return_date | 0 | 62 | 3 date formats |
| return_reason | 0 | 5 | Casing variants; typo "damged" → "Damaged" |
| refund_amount | **4 null** | 64 | **4 refunds exceed computed line value** |
| return_status | 0 | 6 | Variants: Approved/APPROVED/approved/Rejected/rejected/Pending |

### 2.7 suppliers_json.txt

| Column | Nulls/Blank | Distinct | Key findings |
|--------|-------------|----------|--------------|
| supplier_id | 0 | 18 (19 rows) | **1 conflicting duplicate** (S004) |
| supplier_name | 0 | 18 | S004 has two different names |
| country | **3 null** | 5 | Some "Unknown" values |
| rating | 0 | 17 | Range 1.6–9.4 — **1–10 scale**; no normalization needed |
| contract_start_date | 0 | 19 | ISO format only |
| is_preferred | 0 | 5 | Y/N/true/True/False |

---

## 3. Critical data quality issues

### 3.1 Date format ambiguity (HIGH SEVERITY)

Slash-delimited dates (`XX/XX/YYYY`) appear in **orders, payments, products, customers** and contain **both** MM/DD/YYYY and DD/MM/YYYY patterns in the same column:

| File/Column | Total slash dates | First component >12 (→DD/MM) | Second component >12 (→MM/DD) | Ambiguous |
|---|---|---|---|---|
| orders.order_date | 163 | 43 | 52 | 68 |
| payments.payment_date | 162 | 56 | 41 | 65 |
| customers.signup_date | 86 | 27 | 26 | 33 |

**Rule proposed (see DECISIONS.md):** Per-value disambiguation:
- If first component > 12 → DD/MM/YYYY
- If second component > 12 → MM/DD/YYYY
- Both ≤ 12 (ambiguous) → **MM/DD/YYYY** as default (supported by the larger unambiguous majority in order dates and payments; documented as an assumption)

### 3.2 Conflicting duplicate keys

| Entity | Dup ID | Nature | Resolution |
|--------|--------|--------|------------|
| customers | C0128, C0034, C0045, C0111, C0098 | Identical rows except email casing (lower vs UPPER) | Normalize email to lowercase → rows become exact dups → keep lowest source row |
| products | P003, P070, P001, P060, P039 | Different names (`Item X` vs `Item X (Revised)`) and prices | Prefer "(Revised)" row; if neither is revised, prefer positive price; tie-break: lowest row number |
| suppliers | S004 | Same ID, different names ("Sinha…" vs "Amble…"), same rating | Keep lowest source row; flag both names in quarantine |

### 3.3 Orphan foreign keys (kept, flagged)

| Relationship | Orphan count | Orphan key pattern | Action |
|---|---|---|---|
| orders.customer_id → customers | 15 orders | C9XXX format | Keep in silver; flag `is_orphan_customer=True` |
| order_items.order_id → orders | 10 items | O9XXXX format | Keep; flag `is_orphan_order=True` |
| order_items.product_id → products | 8 items | P9XX format | Keep; flag `is_orphan_product=True` |
| payments.order_id → orders | 8 payments | O9XXXX format | Keep; flag |
| returns.order_item_id → order_items | 6 returns | OI9XXXXXX format | Keep; flag |
| products.supplier_id → suppliers | 4 products | S92–S98 format | Keep; flag |

**The orphan keys all follow a consistent pattern (4-digit suffix `9XXX`) suggesting they are test or migrated records not in this data extract.**

### 3.4 Business rule violations (quarantine)

| Rule | Count | Entity | Action |
|------|-------|--------|--------|
| Non-positive quantity (`quantity ≤ 0`) | 10 | order_items | Quarantine |
| Negative unit_price | 10 | order_items | Quarantine (all linked to P003 conflicting dup) |
| Discount outside 0–100% | 7 | order_items | Quarantine |
| Non-positive product unit_price | 4 | products | Quarantine |
| Refund > computed line value | 4 | returns | Quarantine |
| `line_total` mismatch > 0.01 | 51 | order_items | Recompute; keep source value |

### 3.5 Categorical standardization targets

**Order status** → canonical: `Completed`, `Pending`, `Cancelled`, `Returned`

| Raw | → Standard |
|-----|-----------|
| completed / COMPLETE / Complted | Completed |
| pending / PENDING | Pending |
| cancelled / Canceled / Cancled | Cancelled |
| returned | Returned |

**Channel** → canonical: `Web`, `App`, `Store`

| Raw | → Standard |
|-----|-----------|
| web / WEB | Web |
| app / APP | App |
| store / In-store / Instore | Store |

**Customer segment** → canonical: `Platinum`, `Gold`, `Silver`, `Bronze`, `Unknown`

| Raw | → Standard |
|-----|-----------|
| PLATINUM / platinum | Platinum |
| Glod / GOLD / gold | Gold |
| Silverr / SILVER / silver | Silver |
| Broze / BRONZE / bronze | Bronze |

**Product category** → canonical: `Fashion`, `Grocery`, `Electronics`, `Sports`, `Home & Kitchen`

| Raw | → Standard |
|-----|-----------|
| fashion / FASHION | Fashion |
| grocery / GROCERY | Grocery |
| electronics / ELECTRONICS / Electornics | Electronics |
| sports | Sports |
| Home and Kitchen / home & kitchen | Home & Kitchen |

**Boolean fields** (`is_active`, `is_preferred`) → `True` / `False`

| Raw True | Raw False |
|----------|-----------|
| Y / yes / true / True / 1 | N / no / False / false / 0 |

**Payment status** → canonical: `Success`, `Failed`, `Pending`, `Refunded`

| Raw | → Standard |
|-----|-----------|
| SUCCESS / success / Succeded | Success |
| FAILED / failed | Failed |
| Pending | Pending |
| Refunded / refunded | Refunded |

**Return status** → canonical: `Approved`, `Rejected`, `Pending`

| Raw | → Standard |
|-----|-----------|
| APPROVED / approved | Approved |
| Rejected / rejected | Rejected |
| Pending | Pending |

**Return reason** → lowercase canonical

| Raw | → Standard |
|-----|-----------|
| Wrong Item / wrong item | wrong item |
| damged | damaged |

---

## 4. Supplier rating scale

Min=1.6, max=9.4, mean=4.59. This is a **1–10 scale**. No conversion required. Document in DECISIONS.md.

---

## 5. Derived fields

### `line_total` recomputation
Rule: `ROUND(quantity × unit_price × (1 − discount_pct/100), 2)` using `Decimal` with `ROUND_HALF_UP`.  
51 rows have a mismatch > 0.01. The source value will be preserved as `source_line_total`.

### Returned quantity
`returns.csv` has no `returned_quantity` column.  
Proposed rule: **assume the full ordered quantity** for each returned order line.  
Rationale: the refund amount in most cases matches or approaches the full line value. 4 exceptions (refund > line value) will be quarantined.  
(See DECISIONS.md §5.)

---

## 6. `promo_code` "NA" values
`orders.promo_code` has 228 values read by pandas as null because they were stored as literal "NA". These mean "no promo applied" and should be treated as null (not a data error).

---

## 6b. Corrections after Phase 2
- "Return before order": the Phase 1 check swallowed parse errors and reported 0. The silver build finds **29** (26 unambiguous). Flagged, kept.
- Product duplicate winner: the "(Revised)" preference above was dropped in favour of the brief's rule (most complete, then deterministic tie-break). See `docs/DECISIONS.md` #4, #5.
- Refunds above line value are **flagged**, not quarantined (#11). Products with price <= 0 are flagged, not quarantined (#5).
- Real orders exist from 2020-2022 (6) and two signups are dated 2027; kept (#13).

## 7. Missing problem statement document
`docs/Ecommerce_Analytics_Usecase.docx` was not found in the repository. The pasted brief is the authoritative problem statement.

---

## 8. Proposed cleansing rules summary

1. **Dates**: parse with an ordered format list; disambiguate slash dates per-value (first >12 → DD/MM; second >12 → MM/DD; both ≤12 → MM/DD default)
2. **Amounts**: strip `₹` and commas before casting to float
3. **Booleans**: normalize to `True`/`False` using explicit map
4. **Segments**: fix typos + normalize casing
5. **Order status**: fix typos + normalize casing  
6. **Channel**: normalize to Web/App/Store
7. **Categories**: fix typos + normalize casing  
8. **Payment/return status**: normalize casing + fix "Succeded"
9. **Conflicting duplicates**: prefer most complete / latest-named row; tiebreak = lowest source row number
10. **Customer near-duplicates**: after email normalization, 5 dup keys collapse to exact dups → de-duplicate by lowest row
11. **Orphan FKs**: keep all rows; set `is_orphan_<entity>` flag
12. **Quarantine**: non-positive qty, negative price, discount out of range, refund > line value
13. **Recompute `line_total`**: using `Decimal(ROUND_HALF_UP)`; preserve source as `source_line_total`
14. **Returned quantity**: full ordered quantity; flag 4 excessive-refund rows
15. **Phone**: strip all non-digit characters
16. **Supplier rating**: 1–10 scale; no change

---

*Next: await Phase 1 review, then proceed to Phase 2 (Bronze + Silver).*
