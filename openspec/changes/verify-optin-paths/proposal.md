# Proposal: Verify the opt-in ingest paths for real

## Why
The 2026-10-28 full default run (`ingest all --seasons 2023`, homelab) exercised 224 datasets. The other 224 registered datasets are opt-in (221) or on demand (3): per-game, per-player stats and all-time pools. They had been unit-tested with fixtures but never run end to end against the live provider in one lake, so schema drift and runtime problems in them were unknown.

## What
Run each opt-in family on the homelab (bounded), fix every defect found at its root, regenerate schemas from wider samples when real data shows drift, and add CLI knobs for the opt-in paths only where missing. Record evidence per family in `tasks.md`.

## Out of scope
Changing the default selection; ingesting all-time pools or all games in bulk (bounded samples only).
