# Proposal: retrosheet-site-datasets (phase 1: transactions and the *0 biography tables)

## Why

The owner asked (2026-11-11) to ingest the Retrosheet files we lack (managers, umpires, transactions, biography) into
one Retrosheet workflow, with CLI tools, typed, nothing dropped. Change `retrosheet-site-files` downloaded the site's
files and compared them with the GitHub mirror: transactions (`tranDB.zip`) and five biography tables inside
`biodata.zip` (managers0, umpires0, coaches0, ballparks0, teams0) are not in the mirror. Three independent opinions
(Opus 5.5, Gemini 3.8 via `agy`, a free `opencode` model) agreed: keep one source, add the datasets as opt-in, phase it.

## What

1. Six registered, strictly typed, **opt-in** datasets: `transactions`, `managers0`, `umpires0`,
   `coaches0`, `ballparks0`, `teams0` (views `retrosheet_transactions`, `retrosheet_managers0`, ...).
2. A `site` ingest unit in the same command (`baseballpy ingest retrosheet -d site` or `-d transactions`). It
   uses the zips in `raw/retrosheet/site_files/` and fetches a missing zip politely (one request every four seconds,
   robots.txt obeyed, stop at the first refusal). A default `ingest retrosheet` never plans a site job.
3. Column types generated from the real files by `scripts/gen_retrosheet_site_schemas.py` (`site_tables.py`).

## Out of scope (recorded, not forgotten)

Player, manager and umpire logs (55,000 CSVs), the Negro Leagues bundle, the event CSV bundles and the 184
official-totals ledgers stay raw files, with their reason, until the owner decides; `catalog find` is a separate small
change; 2026 event files do not exist yet (mirror and site checked 2026-11-11).
