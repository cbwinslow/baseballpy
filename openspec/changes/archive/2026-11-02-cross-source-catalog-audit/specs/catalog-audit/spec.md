# catalog-audit Specification Delta

## Requirements

### Requirement: Cross-Source Reference Parity
The catalog audit MUST verify coverage parity against external baseball packages (pybaseball, baseballr, MLB-StatsAPI) and official OpenAPI documentation; any external dataset or endpoint that is not directly ingestible SHALL be documented with an explicit verdict and evidence.

#### Scenario: Cross-source catalog audit validation
- **GIVEN** the master coverage matrix of datasets across pybaseball, baseballr, and MLB-StatsAPI
- **THEN** every external capability maps to a registered dataset, an existing accessor, or a documented unsupported verdict with evidence.
- Verified by `tests/test_coverage_matrix.py::test_master_coverage_matrix_completeness`.
