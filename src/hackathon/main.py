"""CLI entry point: python -m hackathon --input data/raw/file.csv"""

from __future__ import annotations

import argparse
import logging
from functools import partial

from hackathon.config import DEFAULT_CONFIG, load_config
from hackathon.logging_setup import setup_logging
from hackathon.pipeline import Pipeline
from hackathon.stages.bigquery import ingest_bq, write_bq
from hackathon.stages.ingest import ingest
from hackathon.stages.output import write_output
from hackathon.stages.transform import transform
from hackathon.stages.validate import validate

log = logging.getLogger("hackathon")


def build_pipeline(
    cfg: dict,
    input_path: str | None,
    output_path: str,
    query: str | None = None,
    bq_table: str | None = None,
) -> Pipeline:
    v, t, bq = cfg.get("validate", {}), cfg.get("transform", {}), cfg.get("bigquery", {})
    if query:
        source = lambda _: ingest_bq(query, bq.get("max_bytes_billed"))  # noqa: E731
    else:
        source = lambda _: ingest(input_path)  # noqa: E731
    stages = [
        ("ingest", source),
        (
            "validate",
            partial(
                validate,
                required_columns=v.get("required_columns"),
                allow_empty=v.get("allow_empty", False),
            ),
        ),
        ("transform", partial(transform, drop_duplicates=t.get("drop_duplicates", True))),
        ("output", partial(write_output, path=output_path)),
    ]
    if bq_table:
        disposition = bq.get("write_disposition", "WRITE_TRUNCATE")
        stages.append(
            ("output_bq", partial(write_bq, table=bq_table, write_disposition=disposition))
        )
    return Pipeline(stages)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the pipeline")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--input", help="Overrides input.file from config")
    parser.add_argument("--output", help="Overrides output.file from config")
    parser.add_argument("--query", help="BigQuery SQL as input; overrides bigquery.query")
    parser.add_argument("--bq-table", help="Also load results into this BigQuery table")
    args = parser.parse_args(argv)

    setup_logging()
    cfg = load_config(args.config)
    input_path = args.input or cfg.get("input", {}).get("file")
    output_path = args.output or cfg.get("output", {}).get("file")
    bq = cfg.get("bigquery", {})
    query = args.query or bq.get("query")
    bq_table = args.bq_table or bq.get("destination_table")
    if not input_path and not query:
        parser.error(
            "No input: pass --input/--query or set input.file/bigquery.query in the config"
        )

    result = build_pipeline(cfg, input_path, output_path, query, bq_table).run()
    log.info("finished: %d rows -> %s", len(result), output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
