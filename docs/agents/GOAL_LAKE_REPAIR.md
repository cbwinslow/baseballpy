# Goal-Seek Prompt: Lake Repair and Freeze (filled in)

This is `docs/agents/GOAL_SEEK_PROMPT.md` with the three blanks filled in. Paste everything below the line into a fresh session. The rules of the template (sections 0 to 4: contract, loop, reporting, web research, definition of done) apply in full; this file adds the goal, the known facts and the safety rules for this job.

---

## GOAL

Make the data lake clean, complete and safe to build on: repair the damaged MLB rows, rewrite the mixed-shape MLB tables with `baseballpy compact`, prove the result with the layout check, and freeze the layout so modelling and the website can start. Work linearly (no Claude subagents).

Scope (each item becomes an OpenSpec change and a BACKLOG row first; claim it on the board):

1. **MLB 2019 `game_boxscore_players` is damaged.** `baseballpy catalog layout --source mlb_api` reports 9 ORPHAN_COMPACT findings (`season=2019/compact-0007` to `compact-0015`, about 1,900 chunks the records point at are not in those files). Records say COMPLETED, so a normal run skips them. Repair it, then root-cause how a compact lost them and add a test or guard so it cannot happen again (a compact must never drop rows; compare row counts before and after).
2. **Three small orphans in season 2023:** `team_roster_all_time`, `team_roster_coach`, `award_recipients` (`compact-0001` each lacks one chunk). Same repair and the same root-cause question.
3. **MLB 2011 stage failed** in `.baseballpy/state/queue.json` (HTTP 500 from `statsapi.mlb.com` for old games such as 308207 on the feed and boxscore routes). Find out (probe, web-search pybaseball/baseballr/sportsdataverse) whether MLB simply has no data for those games. If so, record them as `empty` or `unsupported` with probe evidence and a date, and stop retrying them. Never skip silently.
4. **Eight mixed-shape MLB game tables** (`game_feed_plays`, `game_feed_play_events`, `game_feed_officials`, `game_boxscore_players`, `game_boxscore_officials`, `game_boxscore_top_performers`, `game_win_probability`, `game_play_by_play`; 11k to 27k files each, older files lack newer `*_name_slug` and `review_details_*` columns): run `baseballpy compact` one table at a time.
5. **Freeze and record** the Statcast and Retrosheet layouts (they are clean after the last compact) in `docs/DATA_WORKFLOW.md`, and write the layout check result as evidence.

Anything else you find becomes a new OpenSpec proposal, not an edit.

## Known facts (verified 2026-11-11; re-check before relying on them)

- Lake root: `C:\Users\blain\projects\baseballpy\.baseballpy` (`BASEBALLPY_HOME` unset). Raw files are kept (ADR 97); never delete or rewrite raw.
- Free disk was about 13 GB. The queue's stop line is 4 GB (`--min-free-gb 4`). A compact needs spare room for its output. Check `df` before every step and stop at 6 GB free.
- Retrosheet and Statcast pass the layout check (no MIXED_SCHEMA, ORPHAN, TINY or EMPTY). The last compact rewrote 264 Retrosheet files with matching row counts; a backup of two tables is in the session scratchpad.
- The processed per-dataset record file `_manifest.json` has only an in-process lock (`core/stores.py`). Two processes writing the same dataset can lose records.
- `baseballpy ingest mlb_api -s 2019 -d game_boxscore_players` plans one job. A normal run trusts the records (COMPLETED) and will not refetch. It is not yet known whether `--refresh` reads saved raw files or downloads again; the first step is a 3-game trial (`--limit 3`).
- 2019 `game_feed_plays` is consistent: 2,965 records, all pointing at existing compact files.

## Safety rules for this job (on top of the template)

1. **Do not run while the queue writes.** A process `baseballpy run plans/mlb-games-history.toml --every 24h --retries 5 --min-free-gb 4` and a `backfill ... --stage "games 2011"` child may still be running. The owner said to keep it running. Do not kill it. Wait until no `backfill` process exists (check `Get-CimInstance Win32_Process`), or ask the owner to pause it. Never use broad process kills; stop only background jobs you started, with the task-stop tool.
2. **Back up before rewrite.** Before the first `compact` of a table, copy one small table or one season to the scratchpad, compare row counts and a sample hash after, and only then continue. Record the counts.
3. **One table, one season, one writer at a time.** After each step run `baseballpy catalog layout --source mlb_api` and read the finding for that table.
4. **Ask before deleting** anything, and use the least destructive option. Report free disk after each step.
5. Preflight and claim: `docs/agents/AGENT_BOARD.md`, `baseballpy agent claim <task_id>`, release with `baseballpy agent release <task_id> "<summary>"`.
6. Reuse check (`docs/agents/TOOLING.md`) before any new code: prefer the existing `compact`, `ingest --refresh` and `catalog layout`; custom code needs a sentence of evidence for what they cannot do.

## Order of work

1. Preflight: board, queue state, disk, running processes. Write the OpenSpec change(s) and BACKLOG rows.
2. Trial: `--refresh --limit 3` on 2019 `game_boxscore_players`. Say whether it used raw or the network and how long it took per game. If it uses the network, estimate hours for about 1,900 games and ask the owner before running it.
3. Repair 2019 `game_boxscore_players`, then the three 2023 tables. Re-run the layout check. Root-cause the lost rows and add the guard test.
4. Probe and decide the 2011 failures (item 3 of the scope). Update the queue plan only through the project's own mechanisms.
5. Compact the eight tables one by one, with backups and row-count checks.
6. Final layout check for `mlb_api`, `statcast` and `retrosheet`, `uv run baseballpy db sync`, and the four gates plus `docs generate --check` and `openspec validate --specs`.
7. Update `docs/DATA_WORKFLOW.md` (frozen layouts), archive the changes, commit per slice with the attribution line, do not push.

## Final report (plain words, per `CLAUDE.md`)

Summary first, then: repaired and verified (with counts), done but not verified, not done and why, decisions needed from the owner (options, pros, cons, your pick), details last (commands, file names, numbers).
