# Usage: what is used, why, and how it beats the alternatives

> This file is kept up to date with every change made to the repo.
> Last updated: 2026-10-11 (added BigQuery source/sink; GCP project set to gitbooster).

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

## Change log

- 2026-10-10: Initial version. Added `pyarrow` and `openpyxl` to `pyproject.toml` (the ingest stage listed `.parquet` and `.xlsx` but had no engine to read them). Created `.venv`, `README.md`, `LICENSE` (MIT) and this file.
- 2026-10-11: Changed `GCP_PROJECT_ID` in `.env.example` to `gitbooster`. Added `google-cloud-bigquery` and `db-dtypes`, `src/hackathon/stages/bigquery.py` (`ingest_bq`, `write_bq`), a `bigquery:` block in `config/config.yaml`, and `--query` / `--bq-table` CLI flags in `main.py`. File input still works as before.
