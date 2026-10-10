"""CLI entry point: python -m hackathon --input data/raw/file.csv"""

from __future__ import annotations

import argparse
import logging
from functools import partial

from hackathon.config import DEFAULT_CONFIG, load_config
from hackathon.logging_setup import setup_logging
from hackathon.pipeline import Pipeline
from hackathon.stages.ingest import ingest
from hackathon.stages.output import write_output
from hackathon.stages.transform import transform
from hackathon.stages.validate import validate

log = logging.getLogger("hackathon")


def build_pipeline(cfg: dict, input_path: str, output_path: str) -> Pipeline:
    v, t = cfg.get("validate", {}), cfg.get("transform", {})
    return Pipeline(
        [
            ("ingest", lambda _: ingest(input_path)),
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
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the pipeline")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--input", help="Overrides input.file from config")
    parser.add_argument("--output", help="Overrides output.file from config")
    args = parser.parse_args(argv)

    setup_logging()
    cfg = load_config(args.config)
    input_path = args.input or cfg.get("input", {}).get("file")
    output_path = args.output or cfg.get("output", {}).get("file")
    if not input_path:
        parser.error("No input file: pass --input or set input.file in the config")

    result = build_pipeline(cfg, input_path, output_path).run()
    log.info("finished: %d rows -> %s", len(result), output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
