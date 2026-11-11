# Tasks: product-mandate-reproducible-outputs

Order: 1.1 -> 1.2 -> 1.3. Tasks 2.x are follow-ups; each opens its own change when started.

- [x] 1.1 Test first: `tests/test_agent_rails.py::test_the_contract_states_the_product_and_reproducibility_mandate`
  (AGENTS.md has the "Product mission" and "Reproducible outputs" sections with their key rules; CLAUDE.md
  and `openspec/project.md` carry the mission). It fails before the text exists.
  Done when the test fails for the missing sections.
- [x] 1.2 Write the contract text: `AGENTS.md` sections 0 and 15, `CLAUDE.md`, `openspec/project.md`,
  `README.md`; ADR 100; requirement in the `agent-runbooks` spec.
  Done when 1.1 passes, `docs generate --check` and `openspec validate --specs` pass.
- [x] 1.3 Gates, archive and commit: pytest, ruff check, ruff format --check, mypy --strict.
  Done when the output is pasted in `design.md` and the change is archived.
- [ ] 2.1 Rebuild check: run a source's workflow for a small window into a scratch `BASEBALLPY_HOME` and
  compare with the lake (row counts, schema digest, per-chunk content hash); report differences.
  Done when a change `rebuild-check` exists with its design and tests.
- [ ] 2.2 Ingest re-fetches a chunk the records call done whose compacted file lacks it (test, then fix if
  it fails). Done when the test passes.
- [ ] 2.3 The queue stops marking a stage "done" when its after-step failed (it marked MLB 2018 to 2021
  done with `after-stage step exited with 1`). Done when a test shows the stage stays failed and retries.
- [ ] 2.4 Compaction output is deterministic: the same chunks give byte-identical compacted files
  regardless of the order of work. Done when a test compares two runs.
- [ ] 2.5 Determinism audit of each source (what is pinned, what is live, what varies between runs) with the
  result in each `docs/sources/<source>.md`. Done when every source states it.
