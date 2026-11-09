# Design: cross-source-catalog-audit

## 1. Domain & Architecture Analysis

`baseballpy` provides 459 registered datasets across five core sources:
- `mlb_api` (365 datasets, 65 routes)
- `statcast` (38 datasets: MLB pitches, Minor League pitches, 36 leaderboards)
- `lahman` (27 datasets: historical tables 1871-present)
- `retrosheet` (25 datasets: event files, gamelogs, boxscores, rosters, subs, daily splits)
- `chadwick` (4 datasets: register, register_names, register_leagues, register_countries)

External tools map this domain differently:
1. **`MLB-StatsAPI` / `python-mlb-statsapi` / MLB OpenAPI:**
   Focused purely on `statsapi.mlb.com`. They document 65 distinct endpoints. `baseballpy` covers all 65 routes plus 22 live-probed reference routes found only in live inspection.
2. **`pybaseball`:**
   Wraps Statcast search and ~15 leaderboards, Chadwick ID lookups, and Lahman zips, but heavily relies on scraping HTML tables from Baseball-Reference and FanGraphs.
3. **`baseballr`:**
   R-based toolkit wrapping MLB Stats API game/schedule/roster endpoints, Statcast search and ~25 leaderboards, Retrosheet parsing via Chadwick tools, and HTML scraping of FanGraphs and Baseball-Reference.

### Strategy for Third-Party Scraped Data (FanGraphs & Baseball-Reference)
FanGraphs and Baseball-Reference provide aggregated and proprietary metrics (e.g. wRC+, WAR, FIP, park factors). However, scraping their HTML tables:
- Regularly triggers Cloudflare blocks and HTTP 429 / IP rate bans.
- Relies on unstable DOM selectors that break whenever the sites redesign.
- Re-derives metrics from the exact same raw data sources that `baseballpy` already ingests directly: **Statcast pitch tracking** (for batted ball and plate discipline data), **Retrosheet play-by-play** (for historical run expectancy and linear weights), and **MLB Stats API** (for official scoring).
- The matrix explicitly documents these scraped endpoints as "Derived / Not Scraped", identifying the raw `baseballpy` datasets (Statcast pitches, Retrosheet events, Lahman batting) that modelers can use to calculate or train equivalent metrics.

## 2. Technical Design

### A. Audit Scanner (`scripts/master_coverage_audit.py`)
1. Reads all reference documents in `docs/references/`:
   - `pybaseball.txt`
   - `baseballr.txt`
   - `mlb-statsapi.txt`
   - `python-mlb-statsapi.txt`
   - `mlb-stats-api-openapi.txt`
2. Iterates `baseballpy.core.datasets.DATASETS` (459 datasets) and `baseballpy.sources.mlb_api.endpoints.SUPPORTED`.
3. Maps each external capability to:
   - Target domain / source.
   - External library function(s).
   - `baseballpy` dataset(s) or Python API function.
   - Status (`Supported`, `Partially Supported`, `Derived / Not Scraped`, `Unsupported with Evidence`).
   - Upstream notes (e.g. HTTP 406 on league-wide pools handled by hydrate fallback, minor league pitch tracking availability, etc.).
4. Formats and writes `docs/MASTER_COVERAGE_MATRIX.md`.

### B. Verification Test Suite (`tests/test_coverage_matrix.py`)
1. Validates that every dataset in `baseballpy.core.datasets.DATASETS` is represented in the master matrix.
2. Validates that every route in `ENDPOINT_CROSSCHECK.md` is mapped.
3. Asserts that all unsupported endpoints have non-empty empirical reasons/evidence recorded.

## 3. As Built & Evidence
- Built `scripts/master_coverage_audit.py`: parses reference texts, maps external capabilities against 459 registered datasets, and writes `docs/MASTER_COVERAGE_MATRIX.md`.
- Generated `docs/MASTER_COVERAGE_MATRIX.md` covering all 459 datasets across Statcast (38), MLB API (365), Lahman (27), Retrosheet (25), and Chadwick (4), alongside cross-tool comparison table.
- Added `tests/test_coverage_matrix.py` (3 tests, all passing): validates generator synchronization, 100% presence of all registered datasets in the matrix, and metadata integrity.
- Linked master coverage matrix in `README.md`.
- Merged requirement `Cross-Source Reference Parity` into `openspec/specs/catalog-audit/spec.md`.
