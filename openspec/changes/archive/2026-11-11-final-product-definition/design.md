# Design: final-product-definition

## 1. Evidence (2026-11-11)

- `openspec/project.md` still draws `baseballpy.extract`/`parse`/`sink` and says FanGraphs and Baseball-Reference
  are not implemented; both exist (deferred by ADR 102 for the MLB-first scope).
- Facts gathered this session and now recorded in one place: the lake contract passes for Statcast (pitches and
  leaderboards), Retrosheet (seasons and reference), Chadwick, Lahman and MLB (parts and segments); the raw
  converter dry run on the real lake shows 56% of old MLB raw files are copies; the MLB per-game segment path
  exists (opt-in `--option storage=segments`); Statcast, Retrosheet and the other sources are still on parts.

## 2. Decisions

- The constitution holds the final picture; ADRs hold the reasons; changes hold the work. No new document.
- Layout names stay as decided: parts and compacted files are the old layout (still read and rebuilt), segments
  the target. Users see the same folders and view names in both.
- ADR 107: rebuild from raw, never delete raw, delete old processed only after a verified rebuild.

## 3. As built

- `openspec/project.md`: new section "The Final Product" (pipeline, target layout, one row per source, what users can
  rely on, definition of done); the stale "planned, not implemented" sentence replaced.
- `openspec/changes/EXECUTION_ORDER.md`: "Road to v1" (done, next code, other sources, owner decisions, queue
  restart, release, open improvements).
- ADR 107 (keep raw; rebuild; delete old processed only after a verified comparison).
- `tests/test_final_product.py` (2; failing first): every registered source has a row, the section names the
  target layout and the definition of done, every first command is a real command naming a registered source.

## 4. Gate evidence (2026-11-11)

See the commit: pytest, ruff check, ruff format, mypy --strict, docs generate --check and openspec validate --specs.
