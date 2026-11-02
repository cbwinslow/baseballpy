# Change Proposal: cross-source-catalog-audit

## 1. Intent & Context
Users and modelers require certainty that `baseballpy` covers all baseball datasets available across the public baseball data ecosystem. External packages such as `pybaseball` (Python), `baseballr` (R), and `MLB-StatsAPI` (Python), alongside the official MLB OpenAPI specification, represent the reference standards for baseball data extraction.

This change establishes an automated, exhaustive **Master Coverage Audit & Matrix** comparing `baseballpy`'s 459 registered datasets against all capabilities of `pybaseball`, `baseballr`, `MLB-StatsAPI`, and the MLB OpenAPI spec. For every dataset or endpoint across MLB Stats API, Statcast, Retrosheet, Lahman, and Chadwick:
1. It maps the external capability to the corresponding `baseballpy` dataset or Python function.
2. It documents the status (`Supported`, `Partially Supported`, or `Unsupported`).
3. For unsupported or refused tables (e.g. HTTP 406 on league-wide pools, or HTML scraping of proprietary third-party sites like FanGraphs/Baseball-Reference), it documents the empirical reason and evidence so that no data is silently omitted without proof.

## 2. Proposed Changes
- **Scanner & Generator (`scripts/master_coverage_audit.py`):**
  A script that parses the cloned and excerpted reference files in `docs/references/`, extracts all public functions and routes, matches them against `baseballpy.core.datasets.DATASETS` and public APIs, and generates a structured cross-source matrix.
- **Master Coverage Matrix Document (`docs/MASTER_COVERAGE_MATRIX.md`):**
  An exhaustive, human-readable markdown specification cataloging every capability across all 5 domains (MLB Stats API, Statcast, Retrosheet, Lahman, Chadwick) plus scraped sources, detailing upstream endpoints, corresponding `baseballpy` access paths, and status.
- **Verification Tests (`tests/test_coverage_matrix.py`):**
  Unit tests that assert the generated matrix covers 100% of `baseballpy`'s 459 datasets and accounts for all external reference routes with verified parity or documented reasons.
- **System Specification Update (`openspec/specs/catalog-audit/spec.md`):**
  Add requirement `Requirement: Cross-Source Reference Parity` specifying that catalog audits must verify cross-source completeness and validate unsupported verdicts.

## 3. Impact & Compatibility
- **Zero Splash Damage:** This change is purely additive. It adds an audit script, documentation, and tests without modifying core runtime protocols or extractors.
- **Fidelity & Transparency:** Users and developers have an authoritative reference proving what data is available, how to access it, and why certain web-scraped endpoints are superseded by official raw data feeds.
