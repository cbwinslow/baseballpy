## ADDED Requirements

### Requirement: Every Route Of The Live Savant Menu Is Registered Or Explained
Every leaderboard route that the live Baseball Savant menu links and that answers data MUST be a registered
leaderboard variant with a strict generated schema, a fixture and a documented row; a route that cannot be ingested
MUST stay listed as unsupported with the request tried and the answer.

#### Scenario: Registry, schemas, fixtures, enum and doc agree
- **WHEN** the leaderboard registry, the generated schemas, the fixtures, the enum and the Statcast doc are compared
- **THEN** every supported variant has all five, every unsupported one has its reason in the doc, and keys are columns of the schema
- Verified by `tests/test_statcast_coverage.py::test_registry_schema_dataset_fixture_and_enum_agree` and `tests/test_statcast_coverage.py::test_statcast_doc_lists_every_variant_and_unsupported_route`.
