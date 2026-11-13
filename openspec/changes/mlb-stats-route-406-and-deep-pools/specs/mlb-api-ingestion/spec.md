## ADDED Requirements

### Requirement: Fallback Pool Chunks Are Provisional
A league-wide stats chunk that the hydrate fallback filled MUST record `via = hydrate` in its manifest entry (`via = direct` when `/v1/stats` filled it), and a chunk written before that field existed MUST be recognised by its `.hydrate.` raw file names. While `/v1/stats` is not known to be refused, a `hydrate` chunk MUST NOT be served from the cache: the next ingest fetches it again on the direct route, because the fallback answers with fewer rows. While the route is known to be refused, the provisional chunk MUST be served and no direct request sent.

#### Scenario: The route comes back after a fallback run
- **WHEN** a pool is ingested while `/v1/stats` answers 406, then again after the remembered refusal has expired and the route answers 200
- **THEN** the first chunk records `via = hydrate` and is served without a request while the refusal stands, the second ingest fetches the pool on the direct route and records `via = direct`, and a third ingest sends no request
- Verified by `tests/test_mlb_coverage.py::test_a_pool_the_fallback_filled_is_fetched_again_when_the_route_may_answer`.

### Requirement: Page-Boundary Lists Are Not Repeated On Rows
The flattener MUST NOT copy the `splitsTiedWithOffset` and `splitsTiedWithLimit` wrapper lists of a stats page onto the rows of that page; the raw page keeps them (ADR 116). A source MAY retire a column on purpose (`retire_columns`), and only a retired column MAY be dropped when an old chunk is aligned or migrated to the current schema.

#### Scenario: A stats page with tied splits is flattened
- **WHEN** a stats page whose wrapper holds tied-split lists is flattened, and an old chunk that still has the two columns is rewritten
- **THEN** no row carries the two fields, the other wrapper fields stay on the rows, the old chunk keeps every row and loses only the retired columns, and any other unknown column is still refused
- Verified by `tests/test_mlb_coverage.py::test_page_boundary_copies_are_not_repeated_on_every_row_of_a_stats_page`, `tests/test_mlb_coverage.py::test_an_old_chunk_with_the_retired_page_boundary_columns_is_aligned_and_other_extras_still_refuse` and `tests/test_mlb_coverage.py::test_migrating_an_old_file_drops_the_retired_columns_and_keeps_every_row`.
