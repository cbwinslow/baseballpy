## MODIFIED Requirements

### Requirement: League-Wide Pools Survive A Refused Pool Route
When `/v1/stats` answers HTTP 406 for a league-wide player pool whose stat type has a per-person
equivalent, the pool MUST be fetched through `/v1/people?personIds=...&hydrate=stats(...)` in batches of
the sport's players. Every multi-value parameter in the hydrate expression (`group`, `type`, `sitCodes`,
`metrics`) MUST be list-encoded (`sitCodes=[vr,vl]`), because the provider silently keeps only the first
value of a comma list inside a hydrate expression; an empty multi-value parameter MUST be omitted. Every
provider response MUST be kept as raw bytes, the splits MUST be normalised with the same schema as the
direct route, and the pool MUST keep every split code the same request returns on the person route.

#### Scenario: A 406 on the pool route
- **WHEN** the direct route answers 406 and the people route answers 200
- **THEN** the pool's rows are stored and the raw hydrate pages are kept
- Verified by `tests/test_mlb_coverage.py::test_a_refused_league_wide_pool_is_fetched_through_people_hydrate`.

#### Scenario: Two situation codes in one hydrate expression
- **WHEN** a pool request carries `sitCodes=vr,vl`
- **THEN** the hydrate expression carries `sitCodes=[vr,vl]` and both codes are requested
- Verified by `tests/test_mlb_coverage.py::test_hydrate_expression_list_encodes_multi_value_parameters`.

#### Scenario: Every served split code is kept
- **WHEN** the person route returns a split for `vr` and a split for `vl`
- **THEN** the pool stores two rows, one per split code
- Verified by `tests/test_mlb_coverage.py::test_hydrate_fallback_keeps_every_split_code`.

## ADDED Requirements

### Requirement: Split Pools Written Before the Fix Are Rebuilt
A stored `stats_stat_splits_*` part whose parser revision predates the list fix MUST be treated as
stale, so the next run fetches it again without `--refresh`. The revision MUST be derived from the
endpoint's stat type, not from a hard-coded dataset-name list, and every other MLB dataset MUST keep
the stored parts it already has.

#### Scenario: A split pool stored by the old fallback
- **WHEN** a split pool part was written under the earlier revision
- **THEN** the next call fetches it again, while a non-split pool written under the same revision is
  still served from the lake
- Verified by `tests/test_mlb_coverage.py::test_a_split_pool_written_before_the_list_fix_is_fetched_again`.

### Requirement: A Pool Without a Person Equivalent Is Refused
A stat type the person route cannot serve MUST be listed in `NO_PERSON_EQUIVALENT` with its measured
evidence. When `/v1/stats` answers 406 for such a pool, the fallback MUST NOT run and MUST NOT store an
empty part: `PoolFallbackUnavailableError` MUST name the stat type and the evidence, and a `keep_going`
run MUST report the refusal while keeping the data it already stored.

#### Scenario: A single-season pool is refused
- **WHEN** a `statsSingleSeason` pool answers 406 and the person route would answer 200 with no splits
- **THEN** the call raises an error naming `statsSingleSeason` and no empty part is stored
- Verified by `tests/test_mlb_coverage.py::test_a_pool_stat_type_without_a_person_equivalent_is_refused`.

### Requirement: An Oversized Hydrate Batch Shrinks
An HTTP 414 on a hydrate batch MUST halve that batch and retry the same players, down to one id; at one
id the error MUST propagate. Every page that answers 200 MUST be kept as raw bytes with a unique name,
and every player MUST be requested exactly once.

#### Scenario: A batch the provider rejects as too long
- **WHEN** a hydrate batch answers 414
- **THEN** the batch is halved and retried until it fits or one id also fails
- Verified by `tests/test_mlb_coverage.py::test_a_414_on_a_hydrate_batch_halves_it`.

### Requirement: The Probe Exercises the Fallback Shape
`baseballpy probe` MUST send the hydrate request the fallback uses, including a multi-value `sitCodes`
list, so a broken list syntax or an unavailable people route fails the probe before a long run starts.

#### Scenario: The fallback canary is part of the probe
- **WHEN** the probe canaries are built
- **THEN** one canary carries `hydrate=stats(...sitCodes=[vr,vl])` and a 406 on it fails the probe
- Verified by `tests/test_probe.py::test_probe_checks_the_hydrate_list_syntax`.
