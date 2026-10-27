## ADDED Requirements

### Requirement: Freshness Policy
Cached datasets MUST be revalidated per a `CachePolicy`. Completed historical seasons are immutable; current-season and reference datasets expire by TTL.

#### Scenario: Current-season schedule expires
- **GIVEN** a current-season schedule cached 20 minutes ago with TTL 15 minutes
- **WHEN** requested without `refresh`
- **THEN** it is re-fetched.

#### Scenario: In-progress boxscore not frozen
- **GIVEN** a boxscore cached while the game was in progress
- **WHEN** requested later
- **THEN** it is re-fetched; once the game is final it is cached as immutable.

### Requirement: Manifest Integrity
Manifests MUST be safe under concurrent writers and MUST NOT silently discard corrupt state.

#### Scenario: Concurrent writers
- **GIVEN** two writers completing different chunks of one manifest
- **THEN** both chunks are present after both save.

#### Scenario: Corrupt manifest
- **WHEN** `manifest.json` is invalid JSON
- **THEN** it is preserved as `manifest.json.corrupt-<ts>` and an error is logged.

### Requirement: Dead-Letter Quarantine
Rows failing coercion MUST be written to `quarantine/<source>/<date>/` with reason and context, and a structured warning MUST be logged.
