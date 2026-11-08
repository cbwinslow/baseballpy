## ADDED Requirements

### Requirement: Text Files Are UTF-8 With LF Line Endings On Every OS
Every text file the library writes MUST be written with an explicit `encoding="utf-8"` and, when written, `newline="\n"`; every text read MUST name its encoding. The repository MUST pin LF line endings in `.gitattributes`.

#### Scenario: Source rules and a written file
- **WHEN** the source is scanned for `read_text`, `write_text` and text-mode `open` calls, and the library writes a file
- **THEN** every call names its encoding, every write names `newline`, `.gitattributes` pins LF, and the written file contains no carriage return
- Verified by `tests/test_portability.py::test_text_files_name_their_encoding`, `tests/test_portability.py::test_written_text_keeps_lf_line_endings`, `tests/test_portability.py::test_text_mode_open_names_encoding_and_newline_when_writing`, `tests/test_portability.py::test_the_repository_pins_lf_for_every_checkout` and `tests/test_portability.py::test_a_file_the_library_writes_has_no_carriage_return`.

### Requirement: Worker Processes Use The Spawn Start Method
Every process pool MUST be created with an explicit `spawn` context, so a parent with HTTP or DuckDB threads behaves the same on every OS.

#### Scenario: No pool relies on the platform default
- **WHEN** the source is scanned for `ProcessPoolExecutor`
- **THEN** every call passes `mp_context`, and nothing calls `fork`
- Verified by `tests/test_portability.py::test_worker_processes_use_spawn_on_every_os`.

### Requirement: Console Output Is UTF-8
The command line MUST switch stdout and stderr to UTF-8 when they use another encoding, replacing what cannot be encoded, and leave UTF-8 streams alone.

#### Scenario: Legacy and UTF-8 consoles
- **WHEN** the streams report cp1252, utf-8 or UTF8
- **THEN** only the cp1252 streams are reconfigured to UTF-8 with replacement
- Verified by `tests/test_portability.py::test_console_output_is_utf8`.
