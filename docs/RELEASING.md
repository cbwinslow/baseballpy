# Releasing

This is a checklist for the owner. Nothing here is run automatically, and the repository never pushes or publishes on its own.

1. **Gates are green** on a clean checkout: `uv run pytest -m "not live"`, `uvx ruff check .`, `uvx ruff format --check .`, `uv run mypy --strict src`, `uv run baseballpy docs generate --check`, `openspec validate --specs`, `uv run mkdocs build --strict`.
2. **Audit the providers**: `uv run baseballpy catalog audit` reports no `MISSING`, `REVIVED` or `ERROR` finding, and `catalog status --gaps` lists only datasets whose note says the provider does not publish that season.
3. **Changelog**: move the `Unreleased` entries of `CHANGELOG.md` under the new version and date.
4. **Version**: set `version` in `pyproject.toml` (the project is still `0.1.0`).
5. **Build and check**: `uv build`, then `uvx twine check dist/*`.
6. **Try it on TestPyPI** first: `uvx twine upload --repository testpypi dist/*`, then install it in a clean environment and run `baseballpy doctor` and `baseballpy ingest lahman`.
7. **Tag and publish** only when the owner decides: `git tag vX.Y.Z` and push the tag. The `Release` workflow (`.github/workflows/release.yml`) then checks that the tag matches `version` in `pyproject.toml`, builds, runs `twine check` and uploads to PyPI with trusted publishing. No API token is stored in the repository or in GitHub.

One-time setup (the owner, on the websites):
- On pypi.org (logged in) open *Your account > Publishing* and add a **pending publisher**: PyPI project name `baseballpy`, owner `cbwinslow`, repository `baseballpy`, workflow `release.yml`, environment `pypi`. (The name `baseballpy` was free on 2026-11-14.)
- On GitHub open *Settings > Environments*, make an environment called `pypi` and, if wanted, add yourself as a required reviewer so every upload waits for your click.
- TestPyPI is optional (a separate account); without it, step 6 is replaced by the clean-environment install test of the built wheel, which was run on 2026-11-14.

The weekly `live` workflow (`.github/workflows/live.yml`) runs `catalog audit` against the real providers; read its last result before releasing.
