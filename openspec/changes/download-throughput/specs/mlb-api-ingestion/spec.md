## ADDED Requirements

### Requirement: A Bulk Download Does Not Pay For The Size Of The Lake At Every Chunk
Recording a chunk MUST NOT copy or scan the dataset's whole manifest, and a bulk run MUST be able to hold manifest saves back and write them in batches. The name-clash check MUST use an index extended with the keys that are new since the last check, and still refuse two chunks that would share a file name (case-insensitively, within one season folder), including chunks recorded by another writer. A deferred manifest MUST show held-back entries to its own process at once, keep them when another writer changes the file, save every N entries and when the block ends, including by an error.

#### Scenario: Deferred saves
- **WHEN** 25 chunks are recorded in a block that saves every 10, an error ends another block, another writer changes the file during a block, and blocks are nested
- **THEN** two saves happen during the first block and one at its end, the entries of the failed block are on disk, no entry is lost, and nested blocks save once at the outermost exit
- Verified by `tests/test_manifest_deferred.py::test_deferred_saves_are_batched_and_visible_at_once`, `tests/test_manifest_deferred.py::test_an_error_inside_the_block_still_saves_what_was_recorded`, `tests/test_manifest_deferred.py::test_a_change_by_another_writer_does_not_lose_held_back_entries` and `tests/test_manifest_deferred.py::test_nested_blocks_save_once_at_the_outermost_exit`.

#### Scenario: The clash check
- **WHEN** chunks are put without any call that copies the manifest, a chunk differs from an existing one only by case, and another writer records a chunk
- **THEN** no copy happens, the case-only clash is refused within its season and allowed in another, and the other writer's chunk is seen
- Verified by `tests/test_manifest_deferred.py::test_a_put_does_not_copy_the_whole_manifest` and `tests/test_manifest_deferred.py::test_the_clash_check_still_sees_chunks_written_by_others_and_removed_ones`.
