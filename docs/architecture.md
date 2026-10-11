# Architecture

> Overall system architecture for the HCL Hackathon Starter — ShopSphere e-commerce analytics platform.

---

## System overview

The project contains **two independent pipelines** that share configuration and utility code:

| Pipeline | Entry point | Purpose |
|----------|-------------|---------|
| **Generic pipeline** | `python -m hackathon --input <file>` | Config-driven ingest → validate → transform → output for any tabular file, with optional BigQuery source/sink |
| **Medallion pipeline** | `python -m hackathon.medallion` | ShopSphere e-commerce data: raw files → bronze → silver (+ quarantine) → quality gates → gold star schema in SQLite |

```mermaid
graph LR
    subgraph "Data Sources"
        CSV["CSV / TSV / JSON\nParquet / XLSX"]
        BQ_IN["BigQuery\n(SQL query)"]
        SHOP["ShopSphere\n7 source files"]
    end

    subgraph "Generic Pipeline"
        direction TB
        I[ingest] --> V[validate]
        V --> T[transform]
        T --> O[output CSV]
        O --> BQ_OUT["output_bq\n(optional)"]
    end

    subgraph "Medallion Pipeline"
        direction TB
        B["bronze\n(raw text copy)"]
        B --> SG1{"schema\ngate"}
        SG1 --> S["silver\n(cleansed, typed)"]
        S --> Q["quarantine\n(rejected rows)"]
        S --> SG2{"reconciliation\n& key gates"}
        SG2 --> G["gold\n(star schema)"]
        G --> SG3{"gold integrity\ngates"}
    end

    CSV --> I
    BQ_IN --> I
    SHOP --> B
    O --> disk["Local file"]
    BQ_OUT --> bq_table["BigQuery table"]
    G --> sqlite["SQLite DB"]
```

---

## Repository layout

```
hcl-hackathon-starter/
├── config/
│   └── config.yaml              # Central settings for both pipelines
├── data/
│   ├── raw/                     # Source files (git-ignored contents)
│   │   └── Ecommerce_Analytics_SourceData/
│   │       └── Ecommerce_Analytics_SourceData/
│   │           ├── customers.csv
│   │           ├── orders.csv
│   │           ├── order_items.csv
│   │           ├── payments.csv
│   │           ├── products.csv
│   │           ├── returns.csv
│   │           └── suppliers.json
│   ├── interim/                 # Scratch / intermediate data
│   └── processed/               # Pipeline outputs (CSV, SQLite DB)
├── docs/
│   ├── architecture.md          # ← this file
│   ├── design.md                # Design decisions and patterns
│   ├── data_model.md            # Gold star schema reference
│   └── DECISIONS.md             # Numbered decision log
├── reports/
│   └── profiling_report.md      # Source data profiling results
├── reports/kpi_outputs/         # Generated KPI CSVs and manifest
├── notebooks/                   # Exploration notebooks
├── src/hackathon/
│   ├── config.py                # YAML + .env loader
│   ├── logging_setup.py         # Logging configuration
│   ├── pipeline.py              # Generic stage runner
│   ├── main.py                  # Generic pipeline CLI
│   ├── stages/                  # Generic pipeline stages
│   │   ├── ingest.py
│   │   ├── validate.py
│   │   ├── transform.py
│   │   ├── output.py
│   │   └── bigquery.py
│   └── medallion/               # ShopSphere medallion pipeline
│       ├── run.py               # Orchestrator + CLI
│       ├── bronze.py            # Raw ingestion layer
│       ├── silver.py            # Cleansing + dedup layer
│       ├── gold.py              # Star schema builder
│       ├── quality.py           # Quality gates
│       ├── common.py            # Shared cleaning helpers
│       └── db.py                # SQLite abstraction
├── tests/                       # pytest suite
├── .github/workflows/ci.yml     # Ruff + pytest on push/PR
├── pyproject.toml               # Dependencies and tooling
├── .env.example                 # Secret template (GCP_PROJECT_ID, LOG_LEVEL)
└── README.md                    # Quick start
```

---

## Technology stack

```mermaid
graph TB
    subgraph "Language & Runtime"
        PY["Python 3.10+"]
    end

    subgraph "Data Processing"
        PD["pandas"]
        STD["stdlib: csv, json,\nsqlite3, decimal, hashlib"]
    end

    subgraph "Storage"
        FS["Local filesystem\n(CSV, Parquet)"]
        SQLITE["SQLite\n(medallion output)"]
        BQ["BigQuery\n(optional cloud sink)"]
    end

    subgraph "Configuration"
        YAML["PyYAML\n(config.yaml)"]
        DOTENV["python-dotenv\n(.env secrets)"]
    end

    subgraph "File Format Support"
        PA["pyarrow (Parquet)"]
        OPX["openpyxl (Excel)"]
        DBDT["db-dtypes\n(BQ date types)"]
    end

    subgraph "Cloud"
        GBQ["google-cloud-bigquery"]
        ADC["Application Default\nCredentials (gcloud)"]
    end

    subgraph "Dev Tooling"
        PYTEST["pytest + pytest-cov"]
        RUFF["ruff (linter)"]
        GHA["GitHub Actions CI"]
    end

    PY --> PD
    PY --> STD
    PD --> FS
    STD --> SQLITE
    GBQ --> BQ
    ADC --> GBQ
```

| Layer | Technology | Why |
|-------|-----------|-----|
| Language | Python 3.10+ | Data engineering standard; every cloud SDK supports it |
| Generic data processing | pandas | Fast prototyping; unified API for CSV/JSON/Parquet/Excel |
| Medallion data processing | Python stdlib (`csv`, `json`, `sqlite3`, `decimal`) | Zero extra dependencies; full control over cleaning logic |
| Local storage | CSV files, SQLite | No infrastructure needed; SQLite gives relational queries out of the box |
| Cloud storage | BigQuery via `google-cloud-bigquery` | Official SDK, ADC auth, cost guard with `max_bytes_billed` |
| Configuration | PyYAML + python-dotenv | Human-readable config with comments; secrets stay out of git |
| CI | GitHub Actions + ruff + pytest | Free, fast, catches broken commits before merge |

---

## Data flow — Generic pipeline

```mermaid
sequenceDiagram
    participant User
    participant CLI as main.py
    participant Config as config.py
    participant Pipeline as pipeline.py
    participant Stages as stages/*

    User->>CLI: python -m hackathon --input file.csv
    CLI->>Config: load_config()
    Config-->>CLI: dict (YAML + .env)
    CLI->>Pipeline: build_pipeline(cfg) → Pipeline
    CLI->>Pipeline: pipeline.run()

    loop Each stage
        Pipeline->>Stages: stage(data)
        Stages-->>Pipeline: transformed data
    end

    Pipeline-->>CLI: final DataFrame
    CLI-->>User: "finished: N rows → output.csv"
```

**Stages in order:** `ingest` → `validate` → `transform` → `output` → `output_bq` (optional)

---

## Data flow — Medallion pipeline

```mermaid
sequenceDiagram
    participant User
    participant CLI as run.py
    participant Bronze as bronze.py
    participant Gates as quality.py
    participant Silver as silver.py
    participant Gold as gold.py
    participant DB as db.py → SQLite

    User->>CLI: python -m hackathon.medallion
    CLI->>DB: connect + reset_database()

    CLI->>Bronze: read_sources(input_dir)
    Bronze-->>CLI: raw columns + rows per entity
    CLI->>Gates: schema_gate() per entity
    Gates-->>CLI: pass/fail

    CLI->>Bronze: write_bronze(conn, sources)
    Bronze-->>DB: bronze_* tables + bronze_load_log

    CLI->>Silver: build_silver(bronze_rows)
    Silver-->>CLI: silver rows + quarantine rows + stats
    CLI->>DB: write silver_* + quarantine_*

    CLI->>Gates: reconciliation + unique_key + positive_quantity
    Gates-->>CLI: pass/fail

    CLI->>Gold: build_gold(silver_rows)
    Gold-->>CLI: dim_* + fact_* rows
    CLI->>Gates: gold_gates (integrity + row counts)
    Gates-->>CLI: pass/fail

    CLI->>DB: write dim_* + fact_* tables
    CLI->>DB: write pipeline_runs + quality_gate_results + run_params
    CLI-->>User: counts per entity + gold row counts
```

**Gate enforcement:** if any gate fails, the pipeline stops immediately and gold tables are **not** written. Failed runs are logged in `pipeline_runs` with status `FAILED`.

---

## Deployment topology

```mermaid
graph TB
    subgraph "Local Development"
        DEV["Developer machine\n(Windows / macOS / Linux)"]
        VENV[".venv (Python virtualenv)"]
        DB["SQLite DB\ndata/processed/shopsphere.db"]
    end

    subgraph "CI"
        GHA["GitHub Actions\nruff + pytest"]
    end

    subgraph "Cloud (Optional)"
        GCP["Google Cloud Platform"]
        BQ["BigQuery\nproject: configured by GCP_PROJECT_ID"]
        ADC["gcloud ADC auth"]
    end

    DEV --> VENV
    VENV --> DB
    DEV --> GHA
    DEV --> ADC
    ADC --> BQ
```

Currently the project runs locally with SQLite output. BigQuery is available as an optional cloud source/sink via the generic pipeline. No Docker, Airflow, or cloud orchestration is included yet — by design, to keep the hackathon setup lightweight.
