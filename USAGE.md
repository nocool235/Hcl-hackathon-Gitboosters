# Usage: what is used, why, and how it beats the alternatives

> This file is kept up to date with every change made to the repo.
> Last updated: 2026-10-11 (added KPI SQL files and the KPI runner; see "KPIs" below).

## Runtime dependencies

| Tool | What it does here | Why it was chosen | Benefit over alternatives |
|---|---|---|---|
| **Python 3.10+** | Language for the whole pipeline | Standard language of data engineering; every cloud SDK supports it | Faster to prototype than Java/Scala (Spark); far richer data ecosystem than Go or Node |
| **pandas** | In-memory DataFrames for ingest, cleaning, output | Fast to write and read; covers CSV/JSON/Parquet/Excel in one API | Simpler and quicker to start than PySpark (no cluster or JVM) for hackathon-sized data; more mature than Polars in connector coverage. Trade-off: data must fit in memory, so move to Polars/Spark for very large data |
| **PyYAML** | Reads `config/config.yaml` | Human-readable config with comments | Easier to edit than JSON (comments, no quotes everywhere) and safer than executable Python config; `safe_load` avoids code execution |
| **python-dotenv** | Loads secrets from a git-ignored `.env` | Keeps API keys and cloud credentials out of code and git | Simpler than a secrets manager for local work; same `os.getenv` code works unchanged when real env vars or a cloud secret store are used in deployment |
| **pyarrow** | Parquet read/write engine for pandas | Parquet is the standard columnar format on S3 / ADLS / GCS and in data lakes | Much smaller and faster to query than CSV, keeps column types, supports partitioning. Chosen over fastparquet for broader support and being the Arrow standard shared by Spark, Polars and DuckDB |
| **google-cloud-bigquery** + **db-dtypes** | `stages/bigquery.py`: run SQL as pipeline input (`--query`) and load results to a table (`--bq-table`) | Official SDK; uses Application Default Credentials, so no keys in the repo and each teammate uses their own Google login via IAM | Simpler than the REST API or JDBC drivers; `to_dataframe()` plugs straight into the pandas stages. `maximum_bytes_billed` guards cost. `db-dtypes` supplies the pandas types for BigQuery DATE/TIME columns |
| **openpyxl** | Reads `.xlsx` files for pandas | Business datasets often arrive as Excel | Pure Python and actively maintained; avoids the need for Excel installed (unlike COM automation) and replaces the deprecated xlrd for `.xlsx` |

## Dev and delivery tooling

| Tool | What it does here | Why it was chosen | Benefit over alternatives |
|---|---|---|---|
| **pytest** (+ pytest-cov) | Test runner and coverage | Plain `assert` tests, fixtures like `tmp_path` | Less boilerplate than `unittest`; huge plugin ecosystem |
| **ruff** | Linter (rules E, F, I, B, UP) | One fast tool for linting and import sorting | Replaces flake8 + isort + pyupgrade, and runs 10-100x faster, so CI stays quick |
| **GitHub Actions** (`ci.yml`) | Runs ruff and pytest on every push / PR | Free, built into GitHub, no server to maintain | Zero setup compared with Jenkins; catches broken commits before teammates pull them |
| **setuptools + pyproject.toml** | Packaging and `pip install -e .` | Standard PEP 621 metadata in one file | No extra tool to learn (unlike Poetry/Hatch); editable install makes `import hackathon` work from tests and the CLI |
| **.editorconfig / .gitattributes** | Consistent indentation and LF line endings | Team members use different editors and OSes (Windows here) | Prevents noisy whitespace and CRLF diffs and merge conflicts |
| **.gitignore** | Excludes `.venv`, `.env`, datasets, logs | Avoid leaking secrets and committing large data | Keeps the repo small and safe; `.gitkeep` files preserve the folder structure |

## Design choices

| Choice | Why | Benefit over the alternative |
|---|---|---|
| **Tiny custom `Pipeline` class** (list of `(name, function)`) | Each stage is a plain function: data in, data out | Far less to learn than Airflow, Prefect or Dagster, so you can ship in hours. Each stage is easy to unit test. Per-stage timing and error logging are built in. Stages can later be moved into an orchestrator as-is |
| **Config in YAML, overridable from the CLI** | Change paths and rules without editing code | Teammates can tune behavior safely; CLI flags beat hard-coded paths |
| **Validate stage that fails fast** | Raises on empty data or missing columns | Catching bad input early is cheaper than debugging wrong output downstream, which matters in data quality scoring |
| **Extension-based reader table in `ingest.py`** | One dict maps file type to reader | Adding a format is one line; simpler than a class hierarchy |
| **`src/` layout** | Code lives in `src/hackathon/` | Stops tests accidentally importing the working directory instead of the installed package |
| **Standard `logging` with `LOG_LEVEL`** | One setup function | No extra dependency; works with cloud log collectors (CloudWatch, Azure Monitor, Cloud Logging) that read stdout |

## Local environment

- A virtual environment is in `.venv/` (git-ignored). Created with `python -m venv .venv` and populated with `pip install -e ".[dev]"`.
- Why a venv: isolates project dependencies from the system Python so versions match CI and teammates.

## Not included yet (add if the challenge needs them)

| Candidate | Use when | Why not included by default |
|---|---|---|
| boto3 / azure-storage-blob / google-cloud-storage (BigQuery is already included) | Reading or writing S3 / ADLS / GCS | Depends on which cloud the hackathon uses |
| PySpark or Polars | Data too big for pandas | Adds weight; pandas is faster to start with |
| DuckDB | SQL over Parquet/CSV locally | Optional, easy to add later |
| Docker | Packaging for deployment | Add once the pipeline is stable |
| Airflow / Prefect | Scheduled, multi-step orchestration | Overkill for the starting skeleton |

## Code walkthrough

The pipeline runs in this order: **ingest → validate → transform → output → (output\_bq)**. Each stage is a plain function (`data in → data out`) wired together by the `Pipeline` runner.

### File overview

| File | Use case |
|------|----------|
| [`config.py`](src/hackathon/config.py) | Loads `config/config.yaml` and injects `.env` secrets into the environment |
| [`logging_setup.py`](src/hackathon/logging_setup.py) | One-time setup of Python `logging`; level set via `LOG_LEVEL` env var |
| [`pipeline.py`](src/hackathon/pipeline.py) | Runs an ordered list of `(name, function)` stages with per-stage timing and error logging |
| [`main.py`](src/hackathon/main.py) | CLI entry point — parses args, loads config, builds the stage list, runs the pipeline |

#### Pipeline stages (`src/hackathon/stages/`)

| File | Stage name | Use case | Key functions |
|------|-----------|----------|---------------|
| [`ingest.py`](src/hackathon/stages/ingest.py) | `ingest` | Reads a local file (CSV, TSV, JSON, Parquet, XLSX) into a DataFrame by file extension | `ingest(path)` |
| [`validate.py`](src/hackathon/stages/validate.py) | `validate` | Fails fast on empty data or missing required columns | `validate(df, required_columns, allow_empty)` |
| [`transform.py`](src/hackathon/stages/transform.py) | `transform` | Normalises column names to `lower_snake_case` and optionally drops duplicates | `transform(df, drop_duplicates)` |
| [`output.py`](src/hackathon/stages/output.py) | `output` | Writes the DataFrame to disk as CSV, auto-creating parent directories | `write_output(df, path)` |
| [`bigquery.py`](src/hackathon/stages/bigquery.py) | `ingest` / `output_bq` | BigQuery source (SQL query → DataFrame) and sink (DataFrame → table). Auth via Application Default Credentials | `get_client(project)`, `ingest_bq(query)`, `write_bq(df, table)` |

#### Configuration files

| File | Use case |
|------|----------|
| [`config/config.yaml`](config/config.yaml) | Central settings — paths, required columns, transform toggles, BigQuery options |
| [`.env.example`](.env.example) | Template for secrets (`GCP_PROJECT_ID`, `LOG_LEVEL`). Copy to `.env` (git-ignored) |
| [`pyproject.toml`](pyproject.toml) | Dependencies, packaging, and tool config (ruff, pytest) |

### How the pieces connect

1. `main.py` calls `load_config()` → reads YAML + `.env`
2. `build_pipeline()` assembles the stage list using `functools.partial` to bind config values
3. If `--query` is passed, the ingest stage calls `ingest_bq()` instead of the file-based `ingest()`
4. If `--bq-table` is passed, an extra `output_bq` stage is appended after the CSV write
5. `Pipeline.run()` executes each stage in order, logging timing and catching errors

---

## ShopSphere medallion pipeline (`src/hackathon/medallion/`)

Raw files -> **bronze** -> **silver** (+ **quarantine**) -> **quality gates** -> **gold** star schema, in a local SQLite file.
The older generic pipeline above is untouched and separate. The medallion code uses only the standard library
(`csv`, `json`, `sqlite3`, `decimal`, `hashlib`) plus `pyyaml`/`python-dotenv` via `config.py`; it does **not** use pandas. BigQuery is used only by the optional gold load (`bq_load.py`, behind `--bq-dataset`); the core run never needs it.

| File | Use case |
|---|---|
| [`db.py`](src/hackathon/medallion/db.py) | The only module that touches SQLite (connect, write table, reset). Swap it to change database |
| [`common.py`](src/hackathon/medallion/common.py) | Cleaning helpers: dates (explicit formats, per-value DD/MM vs MM/DD), amounts, booleans, phones |
| [`bronze.py`](src/hackathon/medallion/bronze.py) | Reads the 7 files as text, adds lineage columns, writes `bronze_*` and `bronze_load_log` |
| [`silver.py`](src/hackathon/medallion/silver.py) | One cleansing function per entity, quarantine with reason codes, duplicate-winner rule, orphan flags |
| [`quality.py`](src/hackathon/medallion/quality.py) | Gates: schema drift, reconciliation, unique keys, positive quantity, gold integrity and row counts |
| [`gold.py`](src/hackathon/medallion/gold.py) | Builds 4 dimensions and 4 facts with deterministic hash surrogate keys |
| [`run.py`](src/hackathon/medallion/run.py) | Orchestrates the run, writes `pipeline_runs`, `quality_gate_results`, `run_params`; CLI |
| [`bq_load.py`](src/hackathon/medallion/bq_load.py) | Optional: loads the 8 gold tables into a BigQuery dataset with explicit column types (real `DATE`/`BOOL`), `WRITE_TRUNCATE` so reruns do not duplicate. Reuses `get_client` from `stages/bigquery.py` |

Concepts: **quarantine** (rejected rows kept with a reason, so bronze = silver + quarantine), **quality gate** (a failed check stops the run before gold is written),
**idempotency** (every table except `pipeline_runs` is dropped and rebuilt, so reruns match), **deterministic tie-break** (completeness, then content hash, then source row),
**SCD Type 2** columns on `dim_customer` (the single snapshot cannot show history). See [`docs/data_model.md`](docs/data_model.md) and [`docs/DECISIONS.md`](docs/DECISIONS.md).

Run (PowerShell, from the project root):

```powershell
.venv\Scripts\python.exe -m hackathon.medallion            # prints bronze/silver/quarantine counts per entity and gold row counts
.venv\Scripts\python.exe -m hackathon.medallion --batch-id batch_002 --db-path data/processed/other.db
```

Load gold into BigQuery (optional; needs `gcloud auth application-default login` and `GCP_PROJECT_ID` in `.env` or the environment):

```powershell
$env:GCP_PROJECT_ID = "your-gcp-project-id"      # or set it in .env
.venv\Scripts\python.exe -m hackathon.medallion --bq-dataset shopsphere_gold
# last line printed: bigquery: {'dim_customer': 159, ... 'fact_returns': 65}
```

The load runs only after the local run succeeded (gates passed). If it fails the local database is still fine and the exit code is 2.
Validated with a configured BigQuery project: row counts matched SQLite and a rerun did not duplicate rows.

Config keys (`medallion:` in `config/config.yaml`): `input_dir`, `db_path`, `batch_id`, `reference_date` (null = latest order date), `return_rate_min_volume`, `payment_tolerance`, `repeat_window_days`, `bq_dataset` (null = no load), `bq_location`. Each has a CLI flag.
The BigQuery load also copies the seven `quarantine_*` tables (all STRING columns, `_row_number` INT64), so the
rejected rows can be inspected in BigQuery and KPI 8 can count the duplicate payment rows removed in silver.
Medallion integration tests: [`tests/test_medallion.py`](tests/test_medallion.py) (runs the pipeline on a synthetic
fixture, then the SQL KPIs on its output).

---

## KPIs (`kpis/` + `src/hackathon/kpis.py`)

KPIs exist once, as SQL. The earlier Python implementation (`hackathon.medallion.kpis`, `reports/kpi_outputs/`)
was removed so there is a single set of numbers.

KPIs are plain SQL over the gold tables (not pandas), one file per KPI. Each file starts with `--` comment lines
(title, then `Label: text` entries); the runner and the dashboard read that header as the KPI's description.
As the problem statement asks, every header has a **`Data quality:`** entry (the data-quality issues resolved
before computing the metric, in silver or in the query) and an **`Alternatives:`** entry (the other reasonable ways
to compute it and why this one was chosen), next to the definition, inclusions, exclusions and assumptions.

| File | Output |
|---|---|
| [`kpi_01_net_revenue_category_month.sql`](kpis/kpi_01_net_revenue_category_month.sql) | Net revenue by category and order month (refunds in the original order month) |
| [`kpi_02_top_customers_net_ltv.sql`](kpis/kpi_02_top_customers_net_ltv.sql) | Top 10 customers by net LTV, tie-break order count then `customer_key` |
| [`kpi_02b_customer_reference_exceptions.sql`](kpis/kpi_02b_customer_reference_exceptions.sql) | Part of KPI 2, not a separate KPI: orphaned and near-duplicate customer references kept out of the ranking (count and value), shown under the KPI 2 ranking in the dashboard |
| [`kpi_03_customer_segment_profile.sql`](kpis/kpi_03_customer_segment_profile.sql) | Customers and AOV per standardised segment |
| [`kpi_04_channel_mom_growth.sql`](kpis/kpi_04_channel_mom_growth.sql) | Month-over-month volume and net revenue growth per channel (`LAG()`, full month calendar, NULL + flag when prior month is 0) |
| [`kpi_05_product_return_rate.sql`](kpis/kpi_05_product_return_rate.sql) | Top 10 and bottom 10 product return rates above the minimum volume |
| [`kpi_06_supplier_scorecard.sql`](kpis/kpi_06_supplier_scorecard.sql) | Supplier revenue, average return rate, rating normalised on its own scale (> 5 = out of 10, else out of 5); composite 0.40 / 0.30 / 0.30 |
| [`kpi_07_repeat_purchase_rate.sql`](kpis/kpi_07_repeat_purchase_rate.sql) | Repeat-purchase rate; full 90-day window cohort is primary, all customers for comparison |
| [`kpi_08_payment_reconciliation.sql`](kpis/kpi_08_payment_reconciliation.sql) | Per order: successful payments vs order total, under/over-paid, duplicate/conflicting rows (including those quarantined in silver), no payment |
| [`stretch_margin_risk.sql`](kpis/stretch_margin_risk.sql) | Products sold below cost: affected quantity, revenue and shortfall |

Shared rules (written out in each header): net value = recomputed `line_total` minus **Approved** refunds, each
capped at its line; KPI 1/4/5/6 and margin risk use Completed + Returned orders; KPI 2/3/7 use `Completed` only.
### Two engines, one set of KPIs

| Engine | SQL | Runs against | Thresholds come from | Used for |
|---|---|---|---|---|
| **`bigquery`** (default) | [`kpis/bigquery/*.sql`](kpis/bigquery/) | `GCP_PROJECT_ID`.`shopsphere_gold` (loaded by `python -m hackathon.medallion --bq-dataset shopsphere_gold`) | `medallion:` config, passed as query parameters `@return_rate_min_volume`, `@payment_tolerance`, `@repeat_window_days`, `@reference_date` | The CSVs, the report, and the Streamlit dashboard |
| `sqlite` | [`kpis/*.sql`](kpis/) | local `data/processed/shopsphere.db` | the `run_params` table written by the pipeline | Offline runs and the tests (no cloud needed) |

The two folders hold the same KPIs with the same headers; only the dialect differs (`LEAST` vs `MIN(a, b)`,
`FORMAT_DATE` vs `substr`, `DATE_ADD` vs `date(x, '+N days')`, `COUNTIF`, `SAFE_DIVIDE`). Table names are unqualified;
the BigQuery runner sets the job's default dataset, so the same SQL works for any dataset name.
BigQuery stores money as `NUMERIC`. Local gold stores money as TEXT (exact cents), so the SQLite files `CAST` money
to REAL wherever it is compared (refund cap, margin risk); `tests/test_kpis.py` stores money as TEXT too and fails
if a cast is removed. Verified 2026-10-11: both engines give identical results on every row of every KPI (within
one cent of float rounding).

[`kpis.py`](src/hackathon/kpis.py) runs every SQL file in name order, writes `outputs/kpis/<name>.csv` and
`reports/kpi_report.md` (header bullets plus the first rows of each result). With `sqlite` it opens the database
read-only, refuses to run if the latest pipeline run failed, and warns if config thresholds changed since gold was built.

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dev,dashboard]"   # once: streamlit + BigQuery client
.venv\Scripts\python.exe -m hackathon.medallion --bq-dataset shopsphere_gold   # refresh gold in BigQuery
.venv\Scripts\python.exe -m hackathon.kpis                  # BigQuery: CSVs + report
.venv\Scripts\python.exe -m hackathon.kpis --engine sqlite  # offline alternative
```

Verified 2026-10-11 against `gitbooster.shopsphere_gold`: net revenue 18,801,726.41 in both KPI 1 and KPI 4, equal to an
independent `Decimal` calculation from local gold; KPI 2 top 10 identical to the Python KPIs; margin risk 26 products
in both. Each query scans about 40 KB; `bigquery.max_bytes_billed` (1 GB) caps every query.

### Streamlit dashboard ([`src/hackathon/dashboard.py`](src/hackathon/dashboard.py))

```powershell
.venv\Scripts\python.exe -m streamlit run src/hackathon/dashboard.py --server.address localhost
```

Pick a KPI from the dropdown at the top (the 8 KPIs plus the margin-risk stretch report); the page shows its definition, inclusions and exclusions (from the SQL header), runs the
BigQuery SQL live and shows the result table, rows and data scanned, a CSV download and the SQL itself. The sidebar
also sets the dataset and the four thresholds, so you can rerun a KPI with, say, a 30-unit return-rate minimum
without editing config. Results are cached for 10 minutes ("Clear cached results" forces a rerun).
`--server.address localhost` keeps the app private to your machine; without it Streamlit also listens on the network.
Needs the same login as the loader: `GCP_PROJECT_ID` in `.env` and `gcloud auth application-default login`.

Config keys (`kpis:` in `config/config.yaml`, shared with the Python KPIs): `engine`, `bq_dataset`, `bq_sql_dir`, `sql_dir`, `sql_output_dir`, `report_path`, `head_rows`; for `sqlite` the database is `kpis.db_path` (falls back to `medallion.db_path`). `output_dir` belongs to the Python KPIs.
Tests: [`tests/test_kpis.py`](tests/test_kpis.py) builds a tiny gold database (no real data needed) and checks refund capping, Cancelled exclusion, tie-break, exceptions, the zero-prior-month rule, that every SQL file has a header, that every SQLite KPI has a BigQuery twin with the same title, and threshold precedence.

---

## Team analytics app (`src/hackathon/analytics/`)

Streamlit app for Finance, Marketing and Supply Chain. It runs the KPI SQL files (`kpis/bigquery/` on BigQuery, or `kpis/` on the local SQLite gold) through `hackathon.kpis` and shows:

- **RAG status**: Red/Amber/Green tiles per team (`rag_status.py`). Revenue growth uses the last *complete* month (the month of `reference_date` is dropped when partial) and payment matching is judged on Completed orders only. Thresholds are working assumptions: override per metric under `analytics.thresholds` in `config/config.yaml` once each team confirms its targets.
- **Ask the data** (retrieval-augmented Q&A, `qa.py`): BM25 retrieval over the KPI results, each KPI's SQL header (definition, inclusions, exclusions) and `docs/data_model.md`, filtered to the selected team, then answered by Gemini with cited chunks. The model never writes SQL.

```powershell
.venv\Scripts\python.exe -m pip install -e ".[app]"
# .env: GCP_PROJECT_ID, GEMINI_API_KEY (Q&A tab only)
.venv\Scripts\python.exe -m streamlit run src/hackathon/analytics/app.py
```

BigQuery shows whatever was last loaded: after any pipeline change rerun `python -m hackathon.medallion --bq-dataset shopsphere_gold`.

---

## Change log

- 2026-10-11: Silver now fills a blank product category from its sub-category when the sub-category maps to exactly one category (`infer_categories` in `silver.py`; new `category_inferred` flag on silver/gold products, a BOOL in BigQuery, and `CATEGORY_INFERRED` rows in `quality_issues`). 5 products fixed; KPI 1 `Unknown` fell from ~₹2.0M (39 lines) to ₹119,345 (5 lines for product ids missing from the product file); total net revenue unchanged. BigQuery reloaded. DECISIONS.md #24.

- 2026-10-11: One KPI implementation: removed `src/hackathon/medallion/kpis.py` and `reports/kpi_outputs/`; `hackathon-kpis` console script, README, docs and `tests/test_medallion.py` now use the SQL runner; `kpis.output_dir` config key removed. Corrected the SQL KPIs: every header now has `Data quality:` and `Alternatives:` entries; KPI 6 normalises each supplier rating on its own scale (> 5 = out of 10, else out of 5) instead of dividing all by 10; KPI 8 counts duplicate and conflicting payment rows quarantined in silver; SQLite files cast TEXT money (refund cap and margin risk were wrong). `bq_load.py` now also loads the `quarantine_*` tables. DECISIONS.md #17-#19 rewritten, #21-#23 added.

- 2026-10-11: Dashboard KPI picker is now a dropdown; the KPI 2 companion query (excluded customer references) shows inside the KPI 2 page instead of as its own KPI, and its title is now "KPI 2 (companion)". KPI 6 is no longer labelled stretch (it is one of the 8 required KPIs; only margin risk is optional).
- 2026-10-11: KPIs now run on BigQuery. Added `kpis/bigquery/*.sql` (BigQuery dialect, thresholds as query parameters), a `bigquery` engine in `src/hackathon/kpis.py` (now the default; `--engine sqlite` keeps the offline path), `engine` / `bq_dataset` / `bq_sql_dir` config keys, the Streamlit dashboard `src/hackathon/dashboard.py`, and a `dashboard` extra in `pyproject.toml` (streamlit, BigQuery client).

- 2026-10-11: Added SQL KPIs: 10 SQL files in `kpis/` (KPIs 1-8 incl. 2b, supplier scorecard, margin risk), runner `src/hackathon/kpis.py` (`python -m hackathon.kpis`, writes `outputs/kpis/*.csv` and `reports/kpi_report.md`), `tests/test_kpis.py`, and `sql_dir` / `sql_output_dir` / `report_path` / `head_rows` in the shared `kpis:` config block. Merged with the upstream Python KPIs (`hackathon.medallion.kpis`); both are kept.
- 2026-10-11: Added `medallion/bq_load.py`, `--bq-dataset` / `--bq-location` flags and `bq_dataset` / `bq_location` config keys (optional gold load to BigQuery).
- 2026-10-11: Renamed `data/raw/.../suppliers_json.txt` to `suppliers.json` (contents unchanged). Added `src/hackathon/medallion/` (bronze, silver, quarantine, gates, gold, audit log), `medallion:` block in `config/config.yaml`, `*.db`/`credentials*.json` in `.gitignore`, `docs/data_model.md`, `docs/DECISIONS.md`, `reports/profiling_report.md`.

- 2026-10-10: Initial version. Added `pyarrow` and `openpyxl` to `pyproject.toml` (the ingest stage listed `.parquet` and `.xlsx` but had no engine to read them). Created `.venv`, `README.md`, `LICENSE` (MIT) and this file.
- 2026-10-11: Added optional Google Cloud dependencies, BigQuery source/sink support, and `--query` / `--bq-table` flags in `main.py`. File input still works without the optional cloud extra.
