# Design: data-validation-roundtrip

## 1. Evidence: what the check found (real lake, 2026-11-12)

`baseballpy verify-roundtrip` re-reads sampled raw files as text and compares every cell with the stored value.

| Source | Datasets | Clean | Loss | Skipped (reason) |
|---|---|---|---|---|
| Statcast | 50 | 48 | `pitches`, `pitches_minors` (50 decimal columns stored as 32-bit floats) | none |
| Lahman | 27 | 27 | none | none |
| Chadwick | 4 | 3 | `register.key_npb` (leading zeros dropped, 331 people) | none |
| Retrosheet | 43 | 28 | `umpire_logs.temp` 3 cells (the stray `unknown`, quarantined by design) | 11 (events, event-derived tables, box accounts: raw files are Chadwick event files, not CSV) |

Other findings: Retrosheet `box_games` held six info fields in `_extras` for 8,787 games; roster lines without a
position were stored as an empty string; quarantine holds 0 rows for Statcast, Lahman and Chadwick and 19 rows for
Retrosheet (the stray cells of the site logs and umpire logs).

False alarms that shaped the tool: keys that repeat (Lahman awards, game logs) need a multiset comparison; raw windows
that overlap or hold several fetched versions of a row (Statcast minors 2026) can only be checked by key coverage.

## 2. Prior art and reuse check
`verify-sample` (ADR 108) compares our pipeline with itself on a fresh download; the new check compares the pipeline
with the provider's text, which `cache check` (sha256 of raw bytes) cannot. Reused: Arrow compute, `read_csv_strings`,
the registry, the quarantine files, `schema_from_columns` metadata (upstream names, date formats).

## 3. Decisions
- Integer columns are compared by text, floats by value as 64-bit floats, dates by format, text exactly.
- A dataset the tool cannot read is `skipped` with the reason, never clean.
- The lake contract runs the check on every fresh download in the tests.
- Decimals are `float64`, identifiers text (AGENTS.md section 3B).

## 4. Tests
`tests/test_roundtrip.py` (equal cells, 32-bit float, dropped zero, NULL, missing row, unmapped column, skipped, repeated
keys and overlapping windows), `tests/test_schema_rules.py`, `tests/test_infer_types.py`, `tests/test_chadwick.py`,
`tests/test_retrosheet_box.py`, `tests/test_retrosheet.py`, and `tests/lake_contract.py` (every download test).

## 5. Provider specifications read (2026-11-12)
Savant CSV documentation: units for some fields, no types or precision; `plate_x` redefined in 2026; `vy0` listed
twice. Chadwick register README: ids described as the person's identifier on a site, no type or format. Retrosheet
event file specification: info field names, values and sentinels (documented in `docs/sources/retrosheet.md`).

## 6. Gaps found by the Opus 5.5 review, and what was done (2026-11-12)
- The check crashed with MemoryError on `player_batting_logs` (Python lists): now compared in Arrow, 4.3 GB peak, all 21,999 files and 5,771,788 rows; a MemoryError is a skipped verdict.
- Only 3 files were sampled and only one direction was checked: `--full` reads every file and reports `row_extra` (a processed row no raw row explains). Lahman and Chadwick `--full`: 31 of 31 clean, 1,262,295 raw rows.
- True/false columns were skipped silently: now compared; types still not compared (timestamps) are listed in the notes.
- `_extras` only had to be non-empty: it must now hold the column by name.
- Quarantined cells counted as a loss: now a known verdict when the quarantine holds at least as many rows.
- Event-derived tables had no check: rows are counted against raw lines for all 156 seasons (events 15,844,833; postseason 416,864; deduced 278,885; substitutions 1,737,383), all exact.
- Open: compare event values with the original Chadwick C tools on one season; cross-check `boxscores_*` with `playerlogs.zip`; the game-log date parser drops a bad date without quarantining it (to verify).

## 7. Full-lake results and what the first all-source run found (2026-11-12)
- Statcast `pitches` (15,007,133 rows) and `pitches_minors` (4,536,245 rows, 91,845 other-version rows checked by key) equal the raw text after the 64-bit rebuild; the rebuild parsed the stored raw files (no download for 7 of 25 seasons' windows except the 192 requests for windows Savant had split at its row cap).
- Savant's own 2026 files repeat every `hit_into_play` pitch (35,430 rows of 909,080, byte-identical in the raw files): kept and documented (ADR 115).
- Retrosheet rosters: empty fields were `''` (now NULL, revision 2) and 1 name had a leading space; 138,160 rows now equal.
- The first all-source run showed false alarms that the check itself caused and that are fixed: spaces round a cell (a note, both directions), whole numbers written as `2.0`, non-padded dates (`4/19/1966`), and positional matching of re-ordered rows (now a skipped verdict, not a loss).
- FanGraphs `batting`, `fielding` and `pitching` showed 2 cells whose stored `playerteamid` differed from the raw file; the project parser gives the raw value, so the stored rows were stale. `ingest fangraphs --refresh` rebuilt them and all 10 FanGraphs datasets are now clean. Lesson: a plain re-ingest skips unchanged files; `--refresh` re-parses.
- Still open: MLB, Kalshi and Polymarket raw files are JSON and have no reader yet (task 1.5).
- Download contract now covers every source: a fresh (mocked) download into an empty home must pass `assert_lake_contract` for Statcast, Retrosheet (seasons, references and the opt-in retrosheet.org tables), Chadwick, Lahman, MLB, FanGraphs, Baseball Reference, Kalshi and Polymarket (tests named `test_a_fresh_*_download_has_the_lake_shape`); the contract also runs the round-trip check on each downloaded dataset.
- JSON page sources: `core/rawpages.py` counts the distinct ids in the raw pages; Kalshi `events` (55,197) and `markets` (900,555) and Polymarket `events` (11,653) and `markets` (233,923, nested in the event pages) equal the stored rows exactly. Kalshi `series` is not counted (the raw pages list all 4,156 series, the table keeps the 189 MLB ones by the scope rule); `trades`, `candlesticks`, `prices` and `outcomes` have no count rule yet. MLB raw JSON still has no check.

## As built: count rules for trades, candlesticks, outcomes and prices (2026-11-12)

`core/rawpages.py` gained `page_lines` (log line plus body), `distinct_tuples` and `tuples_counter`; `sources/page_counts.py` holds the page shape of each source (Kalshi candlesticks come as one market's series or as a batch of markets; a Polymarket price page knows its token only from the request; outcomes are the entries of each market's outcome list inside the events pages). `baseballpy verify-roundtrip kalshi polymarket -d trades -d candlesticks -d prices -d outcomes --full --json` on the real lake, 933 s: all four `ok`, raw and stored rows equal (trades 110,994,885; candlesticks 14,903,320; outcomes 467,846; prices 16,043,908). Kalshi `series` stays uncounted on purpose (4,156 listed, 189 kept).
