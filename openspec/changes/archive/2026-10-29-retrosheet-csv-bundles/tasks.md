# Tasks: Retrosheet CSV bundles

- [ ] 0. Owner approval to implement (proposal written 2026-10-28; nothing implemented)
- [ ] 1. (2026-10-28: homelab and PC both time out connecting to retrosheet.org; search snippets recorded in design.md; the pages themselves not read) Read the CSV overview/contents pages from retrosheet.org (or, if unreachable, from a copy the owner supplies for exploration only); record the file list, columns and URLs in `design.md` with citations
- [x] 2. Search how others consume the bundles (R `retrosheet` package, `calestini/retrosheet`, `jerryword/retrosheet-csv`, Chadwick) and record it
- [ ] 3. Generator step: download one small season, widen types, write strict schemas (a `gen_*` script, never hand-typed), register datasets with keys
- [ ] 4. Downloader/adapter wiring through `IngestAdapter` (new task names, no change to existing ones), unsupported entries with `tried` and `verified_on` for anything not downloadable
- [ ] 5. Tests (no network), docs page section, column descriptions from the official contents page, licence note
- [ ] 6. Live check for one season; gates; archive
