# Readable lake names

## Why
File names repeated the dataset and the season (`part-award_recipients_2024_AAACMVP.parquet` inside `award_recipients/season=2024/`), and `manifest.json` next to the data made pandas and pyarrow folder reads fail.

## What changes
- `part_filename()` in `core/stores.py` drops the dataset prefix and the season token; `ProcessedStore.part_path` and the layout migration use it; a clash guard refuses two chunks with one file name.
- The manifest is `_manifest.json`; the old name is renamed on first use.
- Owner's request: easy to navigate, readable names, every data tool can read it.
