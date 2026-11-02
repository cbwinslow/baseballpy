## ADDED Requirements

### Requirement: A Refused Pool Route Still Produces a Typed Schema
When the generation probe is refused by the league-wide pool route (HTTP 406 or another provider
error), it MUST sample the same stat type through the hydrate route the runtime fallback uses, and every
field the sampled split objects carry MUST become a typed column of the generated schema rather than
being left to `_extras`. The probe entry MUST record which route produced the sample.

#### Scenario: The split pools are generated from hydrate payloads
- **WHEN** the probe requests a `stats_stat_splits_*` endpoint and the direct route answers 406
- **THEN** the sample is fetched through `/v1/people?hydrate=stats(...)` and the generated schema types
  `game_type`, `num_teams` and `sport_abbreviation`
- Verified by `tests/test_mlb_coverage.py::test_every_fixture_key_has_a_typed_column`.

### Requirement: A Committed Fixture Carries No Untyped Field
Every flattened key of an endpoint's committed fixture MUST be a typed column of that endpoint's
generated schema. A fixture key that only reaches `_extras` at runtime is schema drift and MUST fail the
suite.

#### Scenario: A fixture key is missing from the schema
- **WHEN** the fixtures and the generated schema are compared
- **THEN** every `snake()` key of every fixture maps to a column and the test passes
- Verified by `tests/test_mlb_coverage.py::test_every_fixture_key_has_a_typed_column`.
