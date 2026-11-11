# Tasks: dry-run-estimate

- [x] 1.1 Tests first: `tests/test_ingest_estimate.py` (held vs missing season folders, unknown datasets,
  partitioned and unpartitioned, dataset filter) and the CLI footer and JSON summary. Done when they fail for the
  missing module.
- [x] 1.2 `scripts/measure_dataset_sizes.py` (reads a lake, writes `core/typical_sizes.json`) and the first
  measurement from the real lake. Done when the JSON lists every dataset the lake holds.
- [x] 1.3 `ingest/estimate.py` and the dry-run footer. Done when 1.1 passes.
- [x] 1.4 Spec requirement in `cli-and-ingest`, ADR 106, docs (DATA_WORKFLOW), gates, archive.
  Done when the evidence is in `design.md`.
