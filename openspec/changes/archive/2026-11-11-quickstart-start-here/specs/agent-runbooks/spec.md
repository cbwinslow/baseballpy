## ADDED Requirements

### Requirement: The Quickstart Has A Checked Start-Here Path
`docs/QUICKSTART.md` MUST open with a "Start here" section that takes a new user from install to a first query
in five steps and names a first command per core source; every `baseballpy` command line in it MUST be a real
command of the CLI and every `ingest <source>` a registered source.

#### Scenario: The start-here commands exist
- **WHEN** the section is parsed
- **THEN** each shown command and source exists, so the page cannot describe a command that is gone
- Verified by `tests/test_quickstart.py::test_the_start_here_commands_are_real`.
