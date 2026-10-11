# Usage: what is used, why, and how it beats the alternatives

> This file is kept up to date with every change made to the repo.
> Last updated: 2026-10-11 (added the ShopSphere medallion pipeline in `src/hackathon/medallion/`; renamed suppliers file to `suppliers.json`).

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
$env:GCP_PROJECT_ID = "gitbooster"      # or set it in .env
.venv\Scripts\python.exe -m hackathon.medallion --bq-dataset shopsphere_gold
# last line printed: bigquery: {'dim_customer': 159, ... 'fact_returns': 65}
```

The load runs only after the local run succeeded (gates passed). If it fails the local database is still fine and the exit code is 2.
Tested 2026-10-11: loaded to `gitbooster.shopsphere_gold` (US); row counts matched SQLite and a rerun did not duplicate rows.

Config keys (`medallion:` in `config/config.yaml`): `input_dir`, `db_path`, `batch_id`, `reference_date` (null = latest order date), `return_rate_min_volume`, `payment_tolerance`, `repeat_window_days`, `bq_dataset` (null = no load), `bq_location`. Each has a CLI flag.
Not built yet: KPI SQL files, pytest tests for the medallion package, README, dashboard.

---

## Change log

- 2026-10-11: Added `medallion/bq_load.py`, `--bq-dataset` / `--bq-location` flags and `bq_dataset` / `bq_location` config keys (optional gold load to BigQuery). Ran it against `gitbooster`, dataset `shopsphere_gold`.
- 2026-10-11: Renamed `data/raw/.../suppliers_json.txt` to `suppliers.json` (contents unchanged). Added `src/hackathon/medallion/` (bronze, silver, quarantine, gates, gold, audit log), `medallion:` block in `config/config.yaml`, `*.db`/`credentials*.json` in `.gitignore`, `docs/data_model.md`, `docs/DECISIONS.md`, `reports/profiling_report.md`.

- 2026-10-10: Initial version. Added `pyarrow` and `openpyxl` to `pyproject.toml` (the ingest stage listed `.parquet` and `.xlsx` but had no engine to read them). Created `.venv`, `README.md`, `LICENSE` (MIT) and this file.
- 2026-10-11: Changed `GCP_PROJECT_ID` in `.env.example` to `gitbooster`. Added `google-cloud-bigquery` and `db-dtypes`, `src/hackathon/stages/bigquery.py` (`ingest_bq`, `write_bq`), a `bigquery:` block in `config/config.yaml`, and `--query` / `--bq-table` CLI flags in `main.py`. File input still works as before.
