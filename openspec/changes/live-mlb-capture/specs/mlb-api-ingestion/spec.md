## ADDED Requirements

### Requirement: Every Poll Answer Of A Live Game Is Journalled Before It Is Used
When the live journal is on (`StreamingConfig.journal`, `BASEBALLPY_STREAM_JOURNAL`), the live streamer MUST append every answer of the provider about a game (the full feed, the `timestamps` list, the `diffPatch` answer, including a 304 and a status the HTTP client refuses) to `raw/mlb_api/_live/<game_pk>.journal.zst` and flush it to disk before the answer is decoded or applied. A record that is cut short MUST be cut off and logged as a warning when the journal is opened; a restart MUST continue the same journal with the next sequence number. The streamer's audit record MUST name the journal as its destination. The journal folder MUST be hidden from the readers, the raw converter and the layout audit.

#### Scenario: On disk first, whole records, one journal across restarts
- **WHEN** a game is streamed with the journal on, the last record is cut in the middle, and the game is streamed again
- **THEN** each decoded answer was already in the journal, the cut record is dropped with a warning, the next record follows the last whole one, the sequence has no gap and no restart, the resume watermark still suppresses repeated events, and the layout audit reports nothing
- Verified by `tests/test_live_journal.py::test_every_poll_answer_is_on_disk_before_it_is_used`, `tests/test_live_journal.py::test_a_torn_last_record_is_cut_logged_and_new_records_follow_whole_ones`, `tests/test_live_journal.py::test_a_restart_continues_the_journal_and_repeats_no_event`, `tests/test_live_journal.py::test_the_audit_log_names_the_journal` and `tests/test_live_journal.py::test_the_journal_folder_is_ignored_by_the_layout_audit`.

### Requirement: A Journal Replays Into The Same Events
`replay_events` MUST run the streamer's own code on the journalled answers (no second implementation) and give the same events in the same order as the live run; it MUST write no journal, no resume state and no dead letters, and its audit operation MUST be named `mlb_stream_replay`. A request that is not the recorded one MUST stop the replay with `ReplayDivergedError`.

#### Scenario: Same events, nothing written
- **WHEN** a game that was streamed (also with a refused status on one call) is replayed from its journal
- **THEN** the events equal the live events apart from the time they were received, a status the client refused is raised again, and the resume state file is unchanged
- Verified by `tests/test_live_journal.py::test_a_replay_gives_the_same_events`, `tests/test_live_journal.py::test_a_failed_status_is_journalled_and_replayed` and `tests/test_live_journal.py::test_a_replay_does_not_touch_the_resume_state`.
