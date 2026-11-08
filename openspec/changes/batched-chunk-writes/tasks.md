# Tasks

Superseded by `response-log-segments`; no task here is open. Where each planned task went:

- 1.1 `ProcessedStore.put_batch`: the processed segment writer, `response-log-segments` 3.2
- 1.2 batch buffer with a games-per-batch option: segment size (250 games or 10 minutes), `response-log-segments` 3.2 and 4.4
- 1.3 interruption and resume test: `response-log-segments` 2.1 and 3.1 (journal replay, commit line, start-up clean-up)
- 1.4 benchmark before and after: `response-log-segments` 4.4
- 1.5 merge, ADR, archive: ADR 95 and ADR 96; this folder is archived unmerged by `response-log-segments` 10.2
