# Architecture and data model

## Medallion layers

```
data/raw/Ecommerce_Analytics_SourceData/   (read-only: 6 CSV + suppliers.json)
        |  bronze.read_sources  -> schema-drift gate
        v
BRONZE   bronze_<entity>        exact text copy + _source_file, _row_number, _batch_id, _loaded_at
         bronze_load_log        file name + row count per load
        |  silver.build_silver  (one cleansing function per entity)
        v
SILVER   silver_<entity>        typed, standardised, deduplicated, orphans flagged
QUARANTINE quarantine_<entity>  rejected + losing-duplicate rows: raw JSON, key, reason code
        |  gates: reconciliation, unique keys, no non-positive quantity
        v
GOLD     dim_*, fact_*          star schema (built in memory, gated, then written)
AUDIT    pipeline_runs, quality_gate_results, run_params, quality_issues
```

Code: `src/hackathon/medallion/` (`bronze.py`, `silver.py`, `quality.py`, `gold.py`, `run.py`, `db.py`, `common.py`).
Every run drops and rebuilds all tables except `pipeline_runs`, so reruns give identical content.

## Gold grains

| Table | Grain | Key |
|---|---|---|
| `dim_customer` | one row per customer version (SCD2: `valid_from`, `valid_to`, `is_current`) | `customer_key` (hash of id + valid_from) |
| `dim_product` | one row per product | `product_key`; `supplier_key` FK |
| `dim_supplier` | one row per supplier | `supplier_key` |
| `dim_date` | one row per calendar day (whole months covered) | `date_key` = YYYYMMDD |
| `fact_orders` | one row per order | `order_id` |
| `fact_order_items` | one row per order line (net `line_total` after discount) | `order_item_id` |
| `fact_payments` | one row per payment | `payment_id` |
| `fact_returns` | one row per return (order item, refund, derived returned quantity) | `return_id` |

Surrogate keys are SHA-1 hashes of the natural key, so the same input always yields the same key.
Each dimension has an `Unknown` member with key `-1`. Orphans (e.g. an order whose customer is not in the
customer file) get key `-1` and keep the source id in `customer_id_source`; they are flagged, never dropped.
Orphan returns also use the unknown product key rather than a nullable dimension key.

## SCD Type 2 (honest note)
`customers.csv` is a single snapshot, so every customer has exactly one version
(`valid_from = 1900-01-01`, `valid_to = 9999-12-31`, `is_current = 1`). The supplied data cannot demonstrate history.
If a segment or address changed, the loader would set `valid_to` of the current row to the change date, set
`is_current = 0`, and insert a new row with a new `valid_from` (and so a new `customer_key`).
A point-in-time join is `fact_orders.order_date BETWEEN valid_from AND valid_to` on `customer_id`.
Today `fact_orders` joins to the current version only.

To print the exact DDL: `sqlite3 data/processed/shopsphere.db ".schema"` (or `SELECT sql FROM sqlite_master`).
Column lists are in `GOLD_COLUMNS` in `gold.py`. SQLite gold dimensions and facts have primary keys;
safe dimension foreign keys are enforced by SQLite, while intentionally orphaned natural-key links are
retained through the unknown-member pattern.
Monetary values are calculated with `Decimal` and stored as exact decimal text in SQLite; the
optional BigQuery loader maps those columns to `NUMERIC`.
