# Design: reference documentation

- Context7's REST API needs no key, caps a response at about 500 KB and ignores paging (tested 2026-10-29), so the in-repo copy is an excerpt with topic queries; the complete manuals are the projects' own repositories, cloned shallow on the homelab (disk), pinned by commit in `docs/references/README.md`.
- Excerpts are `.txt` so mkdocs and the docs tests ignore them. Size: about 17 MB of text in the repository (compresses to a few MB in git).
- The Context7 MCP server is configured in the owner's user config (key held there, never in the repository).
- Cross-checking MLB endpoint and type documentation (pybaseball, MLB-StatsAPI, baseballr, the OpenAPI excerpt) against our generated schemas is a follow-up task, below.
