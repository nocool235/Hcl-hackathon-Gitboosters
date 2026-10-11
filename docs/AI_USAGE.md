# AI Usage Log

## Tools used

ChatGPT/Codex was used as an engineering assistant for repository inspection, implementation review,
KPI design, and test generation.

## Representative prompts

1. Review the repository against the ShopSphere e-commerce analytics use case and identify missing
   deliverables, data-quality risks, and reproducibility problems.
2. Implement the eight required KPIs over the curated gold star schema with explicit assumptions,
   including return-rate thresholds, payment reconciliation tolerance, and repeat-purchase windows.
3. Add tests for orphan handling, duplicate resolution, idempotent medallion execution, KPI outputs,
   and optional BigQuery dependency behavior.

## Validation of generated output

The generated cleansing and KPI logic was checked against the source schemas, the profiling report,
the decision log, and the required KPI definitions. The pipeline was run end to end against the
seven supplied files, quality-issue counts were inspected, SQLite primary/foreign-key DDL was
verified, and KPI outputs were spot-checked for revenue, returns, repeat purchase, and payment
reconciliation. A synthetic end-to-end fixture is covered by `tests/test_medallion.py`; the complete
test suite and Ruff checks run in CI. Ambiguous decisions, such as allocating refunds to the sale
month and weighting supplier scores, are recorded in the KPI manifest.
