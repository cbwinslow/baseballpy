# Releasing

This is a checklist for the owner. Nothing here is run automatically, and the repository never pushes or publishes on its own.

1. **Gates are green** on a clean checkout: `uv run pytest -m "not live"`, `uvx ruff check .`, `uvx ruff format --check .`, `uv run mypy --strict src`, `uv run baseballpy docs generate --check`, `openspec validate --specs`, `uv run mkdocs build --strict`.
2. **Audit the providers**: `uv run baseballpy catalog audit` reports no `MISSING`, `REVIVED` or `ERROR` finding, and `catalog status --gaps` lists only datasets whose note says the provider does not publish that season.
3. **Changelog**: move the `Unreleased` entries of `CHANGELOG.md` under the new version and date.
4. **Version**: set `version` in `pyproject.toml` (the project is still `0.1.0`).
5. **Build and check**: `uv build`, then `uvx twine check dist/*`.
6. **Try it on TestPyPI** first: `uvx twine upload --repository testpypi dist/*`, then install it in a clean environment and run `baseballpy doctor` and `baseballpy ingest lahman`.
7. **Tag and publish** only when the owner decides: `git tag vX.Y.Z`, push, upload to PyPI.

The weekly `live` workflow (`.github/workflows/live.yml`) runs `catalog audit` against the real providers; read its last result before releasing.
