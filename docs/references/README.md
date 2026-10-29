# Reference documentation

Documentation of the tools baseballpy uses and of the projects it is compared with (pybaseball,
baseballr, baseball.computer). Written for development reference; upstream licences apply and every
file names its source.

## In this repository: Context7 excerpts (`*.txt`)

Fetched with `uv run python scripts/fetch_reference_docs.py` (Context7's REST API; a response is
capped at about 500 KB, so these are excerpts with several topic queries for the key libraries, not
the complete manuals). Refresh with the same command. The Context7 MCP server is also configured in
the owner's user config for interactive lookups.

## Complete copies: shallow clones on the homelab

Run `bash scripts/clone_reference_docs.sh` (default destination `~/reference-docs` on
`cbwdellr720`; kept outside this repository because of size). State at the last run (2026-10-29):

| Project | Commit | Size |
|---|---|---|
| aiolimiter | `f36fca0` | 868K |
| arrow | `a99464f` | 97M |
| baseball.computer | `1195c59` | 20M |
| baseballr | `e7091c5` | 14M |
| boxball | `e5ff087` | 12M |
| chadwick | `b0002b6` | 1.4M |
| click | `2247b35` | 2.9M |
| dlt | `7857dca` | 50M |
| duckdb-web | `0336580` | 391M |
| httpx | `b5addb6` | 6.0M |
| hypothesis | `5e93693` | 27M |
| MLB-StatsAPI | `4658baa` | 444K |
| msgspec | `7a16ef5` | 6.8M |
| narwhals | `6c7bda0` | 11M |
| polars | `3a2df0f` | 51M |
| pybaseball | `e588989` | 54M |
| pydantic | `6cd4b40` | 18M |
| pydantic-settings | `94150a0` | 2.1M |
| pytest | `a7b2446` | 12M |
| python-mlb-statsapi | `74f337a` | 2.5M |
| respx | `57d8c29` | 1.5M |
| retrosheet | `ee82e50` | 2.5G |
| rich | `9d8f9a3` | 35M |
| tenacity | `32ac68f` | 880K |

`baseball.computer` and `boxball` are the sources for the baseball.computer comparison;
`chadwickbureau/retrosheet` is the pinned Retrosheet tree we already ingest (a shallow clone is large).
