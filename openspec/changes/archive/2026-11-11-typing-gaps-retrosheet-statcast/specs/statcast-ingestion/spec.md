## ADDED Requirements

### Requirement: Leaderboard Types Come From Every Season
The Savant schema generator MUST probe every season from the first Statcast season to the current year, and a season
in which a column has no value at all MUST give no type evidence, so that a column filled in later seasons is typed
from those seasons and never forced to text by empty early ones.

#### Scenario: Probe seasons and empty seasons
- **WHEN** the generator lists its probe seasons and infers the type of a column that one season sends completely empty
- **THEN** the seasons run from the first Statcast season to the current year with no fixed list, and the empty season gives no type while filled seasons give `float64`, `int16` or `string` as their values say
- Verified by `tests/test_typing_audit.py::test_the_savant_generator_probes_every_season_not_a_fixed_list` and `tests/test_typing_audit.py::test_a_season_where_a_column_is_empty_gives_no_type_evidence`.
