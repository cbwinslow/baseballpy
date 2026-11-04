# Design

- `find_project_root()` walks up from the working directory looking for `pyproject.toml` or `.git`; `get_default_base_dir()` uses it after the two environment variables (`core/config.py`).
- Rejected: a fixed path (breaks when the project moves); the package install folder (read-only for installed copies); always `~/.baseballpy` (the old default, kept as the fallback outside a project).
- Risk: running the tool from a sub-project with its own `pyproject.toml` creates a second data folder there; set `BASEBALLPY_HOME` to share one.

## Evidence
- `tests/test_default_home.py` (5 tests) pass; the test fixtures already pin `BASEBALLPY_HOME`, so no other test depends on the default.
- Not verified: a real backfill into the new default folder (B-09 stays with the owner).
