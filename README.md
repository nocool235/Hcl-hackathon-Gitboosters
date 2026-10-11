# ShopSphere E-Commerce Analytics Platform

A small, config-driven data pipeline you can adapt quickly during the hackathon.
Data flows through four stages: **ingest → validate → transform → output**.

See [USAGE.md](USAGE.md) for what each tool is, why it was chosen, and how it compares with alternatives.

## Quick start

Requires Python 3.10+.

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 2. Install the package with dev tools
pip install -e ".[dev]"

# 3. (Optional) local settings
cp .env.example .env

# 4. Run on a dataset
python -m hackathon --input data/raw/dataset.csv
# or, after install:
hackathon --input data/raw/dataset.csv --output data/processed/result.csv
```

Supported input formats: `.csv`, `.tsv`, `.json`, `.parquet`, `.xlsx`.

## Project layout

```
config/config.yaml        Central settings (paths, required columns, options)
data/raw|interim|processed  Dataset folders (contents are git-ignored)
notebooks/                Exploration
src/hackathon/
  main.py                 CLI entry point, wires the stages together
  pipeline.py             Tiny stage runner with timing and error logging
  config.py               YAML + .env loading
  logging_setup.py        Logging configuration (LOG_LEVEL env var)
  stages/                 ingest.py, validate.py, transform.py, output.py
tests/                    pytest suite
.github/workflows/ci.yml  Runs ruff and pytest on every push / PR
```

## Adapting it to the challenge

1. Drop the dataset in `data/raw/` and set `input.file` in `config/config.yaml`.
2. List the columns you expect under `validate.required_columns`.
3. Put problem-specific logic in `src/hackathon/stages/transform.py`.
4. Add a new stage by writing a function that takes data and returns data, then
   add it to the list in `build_pipeline` in `main.py`.

## Development

```bash
pytest          # run tests
ruff check .    # lint
```

## ShopSphere medallion pipeline

The primary implementation runs the seven supplied source files through bronze, silver,
quarantine, quality gates, and gold dimensional tables in SQLite:

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dev,dashboard]"
.venv\Scripts\python.exe -m hackathon.medallion --bq-dataset shopsphere_gold
.venv\Scripts\python.exe -m hackathon.kpis
.venv\Scripts\python.exe -m streamlit run src/hackathon/dashboard.py --server.address localhost
```

1. The pipeline writes `data/processed/shopsphere.db` and loads the gold and quarantine tables into the
   BigQuery dataset `shopsphere_gold` (project from `GCP_PROJECT_ID` in `.env`; log in once with
   `gcloud auth application-default login`).
2. The KPIs are SQL files in [`kpis/bigquery/`](kpis/bigquery/), one per KPI. Each starts with a comment
   header stating the definition, the data-quality issues resolved first, inclusions and exclusions, and
   the assumption made wherever the KPI could be computed another way. The runner executes them on
   BigQuery and writes `outputs/kpis/<name>.csv` plus [`reports/kpi_report.md`](reports/kpi_report.md).
3. The Streamlit dashboard picks a KPI from a dropdown, shows its header and runs the query live.

`python -m hackathon.kpis --engine sqlite` runs the same KPIs offline from [`kpis/`](kpis/) (SQLite
dialect) against the local database; the tests use this path.

## License

[MIT](LICENSE)
