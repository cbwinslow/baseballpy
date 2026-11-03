## ADDED Requirements

### Requirement: Parsing Uses the Machine's Cores Through One Shared Pool
Retrosheet parsing MUST default to a number of worker processes derived from the CPU count and capped at 32 (`parse_workers`; 0 or 1 parses in the calling process). All parse streams of a run MUST share one persistent process pool, a stream MUST keep at most twice the worker count of files in flight, and tables MUST be yielded in input file order so stored rows are identical to a single-process run.

#### Scenario: The default scales with the machine, capped
- **WHEN** a `LakeConfig` is built without `parse_workers` on a machine with N CPUs
- **THEN** `parse_workers` is `min(N, 32)`, and an explicit value (including 0) wins.
- Verified by `tests/test_retrosheet_pool.py::test_default_parse_workers_follow_the_cpu_count_with_a_cap`.

#### Scenario: A pooled parse is identical to an in-process parse
- **GIVEN** several event files
- **WHEN** they are parsed in process and through the shared pool
- **THEN** the tables are equal and in the same order, and the pool is reused by the second stream.
- Verified by `tests/test_retrosheet_pool.py::test_pooled_parse_equals_in_process_parse_in_order_and_reuses_the_pool`.

#### Scenario: A stream keeps a bounded window in flight
- **WHEN** a stream of many files is consumed slowly
- **THEN** no more than twice the worker count of files have been submitted ahead of the consumer.
- Verified by `tests/test_retrosheet_pool.py::test_a_stream_never_runs_more_than_two_times_workers_ahead`.

#### Scenario: A failing file raises and stops the stream
- **WHEN** one file cannot be parsed
- **THEN** the error reaches the caller and queued files of that stream are cancelled.
- Verified by `tests/test_retrosheet_pool.py::test_a_failing_file_raises_and_cancels_the_rest`.
