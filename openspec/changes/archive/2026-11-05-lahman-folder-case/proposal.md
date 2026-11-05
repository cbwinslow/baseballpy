# Lahman folder case

## Why
GitHub's Linux jobs failed for the underscore-names commits (3 tests) while every Windows run passed: Windows ignores letter case in paths, so a request spelled `Parks` and a migrated `Batting` folder looked right there. The extractor wrote `parks` but read manifests and paths from `Parks`; `migrate-layout` still created `Batting`; one unit test reached the network through the new season calendar.

## What changes
- The Lahman extractor resolves any spelling to the one folder before touching a path.
- `migrate-layout` names Lahman folders from the registry (`core/migrate.py` reads `datasets_for`, the CLI fills the registry first).
- Tests compare the real folder names, the adapter test injects a calendar, and the whole suite is run in a case-sensitive folder.
