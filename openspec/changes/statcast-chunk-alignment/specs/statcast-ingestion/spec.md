## ADDED Requirements

### Requirement: Aligned Windows
Persisted pitch windows MUST lie on a fixed per-year grid (block k = January 1 + k x chunk_days, clipped at December 31) independent of the caller's request, so overlapping, nested or adjacent requests never store the same pitch twice. A request MUST return exactly the pitches of its requested `game_date` range.

#### Scenario: Overlapping requests
- **GIVEN** `extract("2024-06-10","2024-06-16")` followed by `extract("2024-06-15","2024-06-15")`
- **THEN** the dataset contains each pitch key exactly once
- **AND** the second call returns only 2024-06-15 pitches.
