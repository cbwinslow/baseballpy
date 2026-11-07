# Design

- **Check, not rename:** nothing needed renaming; the value is that a future dataset with a CamelCase name, a repeated view or no doc file now fails a test, and a renamed dataset that leaves an orphan folder is found by `catalog layout`.
- **View exception:** kept as data in the test (`VIEW_PREFIX`), so a second exception is a visible, reviewed edit. Renaming the 365 MLB views to `mlb_api_*` was rejected: it would break every existing query for no gain.
- **Raw folders:** not audited by the new check because raw-only names are legitimate (inputs of other datasets, documents); the one stale folder is reported to the owner instead of auto-flagged.
