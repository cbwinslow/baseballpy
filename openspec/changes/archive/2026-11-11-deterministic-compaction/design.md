# Design: deterministic-compaction

## 1. Evidence (2026-11-11)

- A scratch script built four chunks in two insert orders and once more: all three builds give the same sha256
  for `compact-0001.parquet`.
- `core/compact.py` sorts chunk keys, batches by input size only, numbers files from what exists in the folder;
  `core/compacted.py::write_compacted` writes zstd with a fixed row-group size and a chunk map in key order.
- Staged compaction (a, b then c, d) leaves two compacted files; one-shot leaves one (ADR 94: a chunk already in
  a compacted file is not read again). The rows are equal; views have no row order, users sort.

## 2. Reuse check

No new code: tests only. The rule goes into the contract (AGENTS.md section 15 rule 1) and the spec.

## 3. Decision

"Deterministic compaction" means: (1) the same chunks in one run give the same bytes, whatever the download
order; (2) a rerun changes nothing; (3) any history of compaction gives the same rows. File grouping may
differ by history and is not part of the guarantee until segments replace compaction.

## 4. As built

- `tests/test_compact_deterministic.py` (3 tests). Sabotage check: with `for key in sorted(keys)` changed to
  `for key in keys` in `core/compact.py`, `test_the_same_chunks_give_byte_identical_files_whatever_the_download_order`
  fails; with the code restored all three pass.
- AGENTS.md section 15 rule 1 reworded; ADR 104; requirement in `lake-access`. No production code changed.

## 5. Gate evidence (2026-11-11)

pytest 1632 passed, 6 skipped; ruff check clean; ruff format 764 files already formatted; mypy --strict no issues in
180 files; docs generate --check up to date; openspec validate --specs 22 passed.
