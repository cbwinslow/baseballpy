## ADDED Requirements

### Requirement: Manifests Are Read And Written As Bytes
A `ManifestTracker` MUST decode its manifest from the file's bytes and encode it straight to bytes for the atomic write, never through a multi-megabyte intermediate string. A manifest that is not valid JSON, not valid UTF-8 or not an object with a `chunks` mapping MUST be preserved as `*.corrupt-<timestamp>` and treated as absent.

#### Scenario: Large and damaged manifests
- **WHEN** a manifest of 20,000 chunks is saved, and a manifest with bytes that are not UTF-8 is read
- **THEN** the extra memory of the save stays under three times the file size, and the damaged file is preserved and treated as absent
- Verified by `tests/test_atomic.py::test_saving_a_large_manifest_does_not_build_a_big_string`, `tests/test_atomic.py::test_a_manifest_that_is_not_utf8_is_preserved_not_lost` and `tests/test_atomic.py::test_manifest_large_entry_msgspec_roundtrip`.
