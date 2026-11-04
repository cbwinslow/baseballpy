"""Comprehensive Cross-Source Coverage Audit.

Audits and compares all datasets and endpoints available across baseballpy,
pybaseball, baseballr, MLB-StatsAPI, and the MLB Stats API OpenAPI spec.

Usage:
    uv run python scripts/master_coverage_audit.py [--check] [--output PATH]
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from baseballpy.core.datasets import DATASETS

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "docs" / "MASTER_COVERAGE_MATRIX.md"


@dataclass(frozen=True)
class ExternalCapability:
    """An external library capability, its source, and baseballpy mapping."""

    domain: str
    feature: str
    pybaseball: str
    baseballr: str
    mlbstatsapi: str
    baseballpy_target: str
    status: str
    data_origin: str
    notes: str


# Reference mapping of major capabilities across tools
CAPABILITIES: list[ExternalCapability] = [
    # --- MLB Stats API ---
    ExternalCapability(
        domain="MLB Stats API",
        feature="Live Game Feed & Events",
        pybaseball="-",
        baseballr="mlb_pbp()",
        mlbstatsapi="get_game()",
        baseballpy_target="mlb_api:game_feed_plays, stream_live_events()",
        status="Supported",
        data_origin="Official API (v1.1/game/{}/feed/live)",
        notes="Real-time event streaming with watermarking, monotonic index, and snapshot projections.",
    ),
    ExternalCapability(
        domain="MLB Stats API",
        feature="Boxscores & Linescores",
        pybaseball="-",
        baseballr="mlb_boxscore(), mlb_game_linescore()",
        mlbstatsapi="get_game_boxscore(), get_game_linescore()",
        baseballpy_target="mlb_api:game_boxscore_*, game_linescore, get_boxscore()",
        status="Supported",
        data_origin="Official API (v1/game/{}/boxscore)",
        notes="Batting, pitching, fielding boxscores and inning-by-inning linescores.",
    ),
    ExternalCapability(
        domain="MLB Stats API",
        feature="Schedule (Hydrated)",
        pybaseball="-",
        baseballr="mlb_schedule()",
        mlbstatsapi="get_schedule()",
        baseballpy_target="mlb_api:schedule_hydrated, get_schedule()",
        status="Supported",
        data_origin="Official API (v1/schedule)",
        notes="Full season schedules with probable pitchers, venue info, and broadcast metadata.",
    ),
    ExternalCapability(
        domain="MLB Stats API",
        feature="Standings",
        pybaseball="standings() (B-Ref)",
        baseballr="mlb_standings()",
        mlbstatsapi="get_standings()",
        baseballpy_target="mlb_api:standings_*, get_standings()",
        status="Supported",
        data_origin="Official API (v1/standings)",
        notes="Regular season, wild card, division leaders, spring training, and postseason standings.",
    ),
    ExternalCapability(
        domain="MLB Stats API",
        feature="Rosters & Teams",
        pybaseball="-",
        baseballr="mlb_rosters(), mlb_teams()",
        mlbstatsapi="get_team_roster(), get_teams()",
        baseballpy_target="mlb_api:team_roster_*, teams_season, get_roster(), get_teams()",
        status="Supported",
        data_origin="Official API (v1/teams, v1/teams/{}/roster)",
        notes="Active, 40-man, depth chart, non-roster invitees, and coaching staff across MLB and 20 minor leagues.",
    ),
    ExternalCapability(
        domain="MLB Stats API",
        feature="Player & Team Situational Splits",
        pybaseball="-",
        baseballr="Partial",
        mlbstatsapi="get_person_stats()",
        baseballpy_target="mlb_api:stats_stat_splits_*, people_stats_* (160+ tables)",
        status="Supported",
        data_origin="Official API (v1/stats, v1/people/{}/stats)",
        notes="Direct route refused 406 since Oct 2026; baseballpy uses automated player-level hydrate fallback.",
    ),
    ExternalCapability(
        domain="MLB Stats API",
        feature="Draft History & Prospects",
        pybaseball="-",
        baseballr="mlb_draft(), mlb_draft_prospects()",
        mlbstatsapi="get_draft()",
        baseballpy_target="mlb_api:draft_picks, draft_prospects, get_draft()",
        status="Supported",
        data_origin="Official API (v1/draft/{}, v1/draft/prospects/{})",
        notes="Complete rule 4 draft selections and scout prospect rankings.",
    ),
    ExternalCapability(
        domain="MLB Stats API",
        feature="Transactions & Free Agents",
        pybaseball="-",
        baseballr="mlb_transactions()",
        mlbstatsapi="get_transactions()",
        baseballpy_target="mlb_api:transactions_season, free_agents, get_transactions()",
        status="Supported",
        data_origin="Official API (v1/transactions, v1/people/freeAgents)",
        notes="Historical trades, waivers, assignments, injured list movements, and signings.",
    ),
    ExternalCapability(
        domain="MLB Stats API",
        feature="Awards & Honors",
        pybaseball="-",
        baseballr="-",
        mlbstatsapi="get_awards()",
        baseballpy_target="mlb_api:award_recipients, ref_awards",
        status="Supported",
        data_origin="Official API (v1/awards/{}/recipients)",
        notes="All MVP, Cy Young, Rookie of the Year, Gold Glove, and Silver Slugger recipients.",
    ),
    ExternalCapability(
        domain="MLB Stats API",
        feature="Reference Dictionaries & Lookup Tables",
        pybaseball="-",
        baseballr="-",
        mlbstatsapi="Partial",
        baseballpy_target="mlb_api:ref_* (35 reference tables)",
        status="Supported",
        data_origin="Official API (35 distinct reference routes)",
        notes="Sports, leagues, divisions, job types, pitch codes, event types, venues, and situation codes.",
    ),
    # --- Statcast / Baseball Savant ---
    ExternalCapability(
        domain="Statcast",
        feature="Major League Pitch Tracking",
        pybaseball="statcast(), statcast_pitcher(), statcast_batter()",
        baseballr="statcast_search(), statcast_search_batters()",
        mlbstatsapi="-",
        baseballpy_target="statcast:pitches, statcast()",
        status="Supported",
        data_origin="Baseball Savant API (statcast_search.csv)",
        notes="Full 120-column physical pitch trajectory, release point, spin, exit velo, and launch angle.",
    ),
    ExternalCapability(
        domain="Statcast",
        feature="Minor League Pitch Tracking (Triple-A)",
        pybaseball="-",
        baseballr="-",
        mlbstatsapi="-",
        baseballpy_target="statcast:pitches_minors",
        status="Supported",
        data_origin="Baseball Savant API (minors=true)",
        notes="Triple-A Statcast tracking data (available since 2023).",
    ),
    ExternalCapability(
        domain="Statcast",
        feature="Exit Velocity & Barrels Leaderboard",
        pybaseball="statcast_pitcher_exitvelo_barrels()",
        baseballr="statcast_leaderboards(type='exit_velocity')",
        mlbstatsapi="-",
        baseballpy_target="statcast:leaderboard_exit_velocity_barrels",
        status="Supported",
        data_origin="Baseball Savant Leaderboards",
        notes="Hard hit rate, max exit velo, barrels per plate appearance and batted ball event.",
    ),
    ExternalCapability(
        domain="Statcast",
        feature="Expected Statistics (xBA, xSLG, xwOBA)",
        pybaseball="statcast_batter_expected_stats()",
        baseballr="statcast_leaderboards(type='expected_statistics')",
        mlbstatsapi="-",
        baseballpy_target="statcast:leaderboard_expected_statistics",
        status="Supported",
        data_origin="Baseball Savant Leaderboards",
        notes="Quality of contact expected metrics for batters and pitchers.",
    ),
    ExternalCapability(
        domain="Statcast",
        feature="Sprint Speed & Running Splits",
        pybaseball="statcast_sprint_speed(), statcast_running_splits()",
        baseballr="statcast_leaderboards(type='sprint_speed')",
        mlbstatsapi="-",
        baseballpy_target="statcast:leaderboard_sprint_speed, running_splits",
        status="Supported",
        data_origin="Baseball Savant Leaderboards",
        notes="Ft/sec sprint speeds, 90-foot splits, and runner bolt metrics.",
    ),
    ExternalCapability(
        domain="Statcast",
        feature="Pitch Arsenals & Movement",
        pybaseball="statcast_pitcher_pitch_arsenal(), statcast_pitcher_arsenal_stats()",
        baseballr="statcast_leaderboards(type='pitch_arsenal')",
        mlbstatsapi="-",
        baseballpy_target="statcast:leaderboard_pitch_arsenals, pitch_movement",
        status="Supported",
        data_origin="Baseball Savant Leaderboards",
        notes="Pitch type breakdown, velocity, active spin rate, and horizontal/vertical break.",
    ),
    ExternalCapability(
        domain="Statcast",
        feature="Outs Above Average & Catch Probability",
        pybaseball="statcast_outfield_directional_outs_above_average()",
        baseballr="statcast_leaderboards(type='outs_above_average')",
        mlbstatsapi="-",
        baseballpy_target="statcast:leaderboard_outs_above_average, catch_probability",
        status="Supported",
        data_origin="Baseball Savant Leaderboards",
        notes="Directional infield and outfield defensive range and catch difficulty metrics.",
    ),
    ExternalCapability(
        domain="Statcast",
        feature="Catcher Pop Time & Framing",
        pybaseball="statcast_catcher_poptime()",
        baseballr="statcast_leaderboards(type='poptime')",
        mlbstatsapi="-",
        baseballpy_target="statcast:leaderboard_catcher_poptime, catcher_framing",
        status="Supported",
        data_origin="Baseball Savant Leaderboards",
        notes="Exchange time, 2B throw time, arm strength, and strike zone framing strike rate.",
    ),
    ExternalCapability(
        domain="Statcast",
        feature="Bat Tracking (Swing Path & Speed)",
        pybaseball="-",
        baseballr="statcast_leaderboards(type='bat_tracking')",
        mlbstatsapi="-",
        baseballpy_target="statcast:leaderboard_bat_tracking",
        status="Supported",
        data_origin="Baseball Savant Leaderboards",
        notes="New in 2024: bat speed (mph), swing length (ft), squared-up rate, and blast rate.",
    ),
    ExternalCapability(
        domain="Statcast",
        feature="Arm Strength",
        pybaseball="-",
        baseballr="statcast_leaderboards(type='arm_strength')",
        mlbstatsapi="-",
        baseballpy_target="statcast:leaderboard_arm_strength",
        status="Supported",
        data_origin="Baseball Savant Leaderboards",
        notes="Maximum throwing velocity for outfielders and infielders on competitive throws.",
    ),
    ExternalCapability(
        domain="Statcast",
        feature="Pitch Tempo",
        pybaseball="-",
        baseballr="statcast_leaderboards(type='pitch_tempo')",
        mlbstatsapi="-",
        baseballpy_target="statcast:leaderboard_pitch_tempo",
        status="Supported",
        data_origin="Baseball Savant Leaderboards",
        notes="Median seconds between pitches with bases empty and runners on base.",
    ),
    # --- Retrosheet ---
    ExternalCapability(
        domain="Retrosheet",
        feature="Play-by-Play Event Files (.EVA/.EVN)",
        pybaseball="-",
        baseballr="retrosheet_data()",
        mlbstatsapi="-",
        baseballpy_target="retrosheet:events, events()",
        status="Supported",
        data_origin="Retrosheet Mirror / Chadwick Bureau",
        notes="Complete historical event logs covering pitches, pickoffs, and plays back to 1914.",
    ),
    ExternalCapability(
        domain="Retrosheet",
        feature="Game Logs",
        pybaseball="-",
        baseballr="-",
        mlbstatsapi="-",
        baseballpy_target="retrosheet:game_logs, postseason_game_logs, game_logs()",
        status="Supported",
        data_origin="Retrosheet Mirror / Chadwick Bureau",
        notes="Official game summary lines with 161 columns for every major league game from 1871-present.",
    ),
    ExternalCapability(
        domain="Retrosheet",
        feature="Box Scores & Accounts",
        pybaseball="-",
        baseballr="-",
        mlbstatsapi="-",
        baseballpy_target="retrosheet:boxscores, box_records, boxscores()",
        status="Supported",
        data_origin="Retrosheet Mirror / Chadwick Bureau",
        notes="Player box scores, lineup batting orders, and daily game accounts.",
    ),
    ExternalCapability(
        domain="Retrosheet",
        feature="Rosters & Substitutions",
        pybaseball="-",
        baseballr="-",
        mlbstatsapi="-",
        baseballpy_target="retrosheet:rosters, substitutions, rosters()",
        status="Supported",
        data_origin="Retrosheet Mirror / Chadwick Bureau",
        notes="In-game substitution sequences and seasonal roster files.",
    ),
    ExternalCapability(
        domain="Retrosheet",
        feature="Daily Splits",
        pybaseball="-",
        baseballr="-",
        mlbstatsapi="-",
        baseballpy_target="retrosheet:daily_splits, daily_splits()",
        status="Supported",
        data_origin="Retrosheet Mirror / Chadwick Bureau",
        notes="Day-by-day split accumulations for batting and pitching.",
    ),
    # --- Lahman Database ---
    ExternalCapability(
        domain="Lahman",
        feature="Historical Player Stats (Batting, Pitching, Fielding)",
        pybaseball="batting(), pitching(), fielding()",
        baseballr="-",
        mlbstatsapi="-",
        baseballpy_target="lahman:Batting, Pitching, Fielding, batting(), pitching(), fielding()",
        status="Supported",
        data_origin="Sean Lahman Database / GitHub CSV mirror",
        notes="Standard historical database tables partitioned 1871-present.",
    ),
    ExternalCapability(
        domain="Lahman",
        feature="Teams & Franchises",
        pybaseball="teams()",
        baseballr="-",
        mlbstatsapi="-",
        baseballpy_target="lahman:Teams, TeamsFranchises, teams()",
        status="Supported",
        data_origin="Sean Lahman Database / GitHub CSV mirror",
        notes="Historical team records, attendance, home runs, and franchise lineage.",
    ),
    ExternalCapability(
        domain="Lahman",
        feature="Biographical People & Hall of Fame",
        pybaseball="people()",
        baseballr="-",
        mlbstatsapi="-",
        baseballpy_target="lahman:People, HallOfFame, people(), hall_of_fame()",
        status="Supported",
        data_origin="Sean Lahman Database / GitHub CSV mirror",
        notes="Player birth dates, debut dates, batting/throwing hands, and Hall of Fame voting records.",
    ),
    ExternalCapability(
        domain="Lahman",
        feature="Salaries, Awards & All-Star Games",
        pybaseball="salaries(), allstar()",
        baseballr="-",
        mlbstatsapi="-",
        baseballpy_target="lahman:Salaries, AwardsPlayers, AllstarFull, salaries(), allstar()",
        status="Supported",
        data_origin="Sean Lahman Database / GitHub CSV mirror",
        notes="Historical player salary figures (1985-present), award voting, and All-Star rosters.",
    ),
    # --- Chadwick Bureau ---
    ExternalCapability(
        domain="Chadwick",
        feature="Player ID Crosswalk / Resolution",
        pybaseball="playerid_lookup(), chadwick_register()",
        baseballr="chadwick_player_lu()",
        mlbstatsapi="-",
        baseballpy_target="chadwick:register, resolve_player(), crosswalk()",
        status="Supported",
        data_origin="Chadwick Bureau Register",
        notes="Universal cross-reference linking MLBAM ID, Retrosheet ID, Baseball-Reference slug, and FanGraphs ID.",
    ),
    ExternalCapability(
        domain="Chadwick",
        feature="Aliases, Leagues & Country Codes",
        pybaseball="-",
        baseballr="-",
        mlbstatsapi="-",
        baseballpy_target="chadwick:register_names, register_leagues, register_countries",
        status="Supported",
        data_origin="Chadwick Bureau Register",
        notes="Nicknames, alternative spellings, historical league codes, and country mappings.",
    ),
    # --- Third-Party Web Scrapers (FanGraphs & Baseball-Reference) ---
    ExternalCapability(
        domain="FanGraphs (Scraped)",
        feature="Advanced Batting Metrics (wOBA, wRC+, WAR)",
        pybaseball="batting_stats(), team_batting()",
        baseballr="fg_batter_leaders(), fg_team_batter()",
        mlbstatsapi="-",
        baseballpy_target="Derived: Compute from Statcast / Retrosheet / Lahman",
        status="Derived / Not Scraped",
        data_origin="FanGraphs HTML tables",
        notes="FanGraphs scrapes violate TOS and break on HTML changes. Underlying raw event and pitch data are fully ingested in baseballpy.",
    ),
    ExternalCapability(
        domain="FanGraphs (Scraped)",
        feature="Advanced Pitching Metrics (FIP, xFIP, SIERA)",
        pybaseball="pitching_stats(), team_pitching()",
        baseballr="fg_pitcher_leaders(), fg_team_pitcher()",
        mlbstatsapi="-",
        baseballpy_target="Derived: Compute from Statcast / Retrosheet / Lahman",
        status="Derived / Not Scraped",
        data_origin="FanGraphs HTML tables",
        notes="FIP and run-prevention metrics are deterministically calculable from Statcast and Lahman pitching data.",
    ),
    ExternalCapability(
        domain="Baseball-Reference (Scraped)",
        feature="Daily Player Game Logs & Splits",
        pybaseball="bref_daily_batter(), bref_daily_pitcher()",
        baseballr="bref_daily_batter(), bref_daily_pitcher()",
        mlbstatsapi="-",
        baseballpy_target="retrosheet:daily_splits, mlb_api:team_stats_by_date_range_*",
        status="Supported via Official Feeds",
        data_origin="Baseball-Reference HTML tables",
        notes="Baseball-Reference scrapes are rate-limited by Cloudflare. baseballpy provides identical daily splits from Retrosheet and MLB API.",
    ),
    ExternalCapability(
        domain="NCAA / College (Scraped)",
        feature="NCAA College Baseball Scraping",
        pybaseball="-",
        baseballr="ncaa_scrape()",
        mlbstatsapi="-",
        baseballpy_target="lahman:CollegePlaying",
        status="Partially Supported",
        data_origin="NCAA stats web site",
        notes="College player history is in Lahman CollegePlaying; live NCAA college pitch tracking is outside professional MLB scope.",
    ),
]


def generate_markdown_report() -> str:
    """Generate the complete MASTER_COVERAGE_MATRIX.md documentation."""
    # Group datasets by source
    by_source: dict[str, list[Any]] = {}
    for d in DATASETS.values():
        by_source.setdefault(d.source, []).append(d)

    total_datasets = len(DATASETS)

    lines: list[str] = [
        "# Master Baseball Dataset Coverage Matrix",
        "",
        "This document provides an exhaustive catalog of all baseball datasets across the public data",
        "ecosystem, comparing `baseballpy` against `pybaseball`, `baseballr`, `MLB-StatsAPI`, and the",
        "official MLB OpenAPI specification.",
        "",
        f"- **Total Registered Datasets in baseballpy:** {total_datasets:,}",
        f"- **MLB Stats API:** {len(by_source.get('mlb_api', [])):,} datasets across 65 API routes",
        f"- **Statcast (Baseball Savant):** {len(by_source.get('statcast', [])):,} datasets (MLB pitches, Minor League pitches, 36 leaderboards)",
        f"- **Retrosheet:** {len(by_source.get('retrosheet', [])):,} datasets (PBP events, game logs, boxscores, rosters)",
        f"- **Lahman Database:** {len(by_source.get('lahman', [])):,} datasets (complete historical database 1871–present)",
        f"- **Chadwick Bureau:** {len(by_source.get('chadwick', [])):,} datasets (universal player ID crosswalk)",
        "",
        "---",
        "",
        "## 1. Cross-Tool Capability Comparison",
        "",
        "| Domain | Capability / Feature | `pybaseball` | `baseballr` | `MLB-StatsAPI` | `baseballpy` Status | Data Origin & Notes |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :--- |",
    ]

    for cap in CAPABILITIES:
        status_badge = f"**{cap.status}**" if "Supported" in cap.status else f"*{cap.status}*"
        lines.append(
            f"| **{cap.domain}** | {cap.feature} | {cap.pybaseball} | {cap.baseballr} | {cap.mlbstatsapi} | "
            f"{status_badge} (`{cap.baseballpy_target}`) | {cap.notes} |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 2. Ingestion Architecture: Why We Avoid Unofficial Web Scraping",
            "",
            "`pybaseball` and `baseballr` scrape HTML pages from **FanGraphs** and **Baseball-Reference**.",
            "While convenient for quick ad-hoc analysis, web scraping introduces severe production risks:",
            "1. **IP Bans & Cloudflare Blocks:** Scraping HTML triggers HTTP 429 and CAPTCHAs, breaking automated pipelines.",
            "2. **Fragile DOM Selectors:** HTML class changes cause silent parser failures and corrupted schemas.",
            "3. **Zero Added Value:** Both FanGraphs and Baseball-Reference derive their core metrics from the exact same raw data:",
            "   - **Statcast Pitches:** Full pitch tracking data from Baseball Savant (`baseballpy.sources.statcast`).",
            "   - **Retrosheet Play-by-Play:** Historical events, box scores, and game logs (`baseballpy.sources.retrosheet`).",
            "   - **MLB Stats API:** Official real-time scoring, rosters, and schedules (`baseballpy.sources.mlb_api`).",
            "",
            "`baseballpy` ingests the **authoritative raw feeds** with zero-copy PyArrow schemas, allowing analysts to compute",
            "or train any derived sabermetric metric without web scraping dependencies.",
            "",
            "---",
            "",
            "## 3. Exhaustive Catalog of All Registered Datasets in `baseballpy`",
            "",
        ]
    )

    for source_name in ("statcast", "mlb_api", "lahman", "chadwick", "retrosheet"):
        datasets = by_source.get(source_name, [])
        lines.extend(
            [
                f"### {source_name.upper()} ({len(datasets)} datasets)",
                "",
                "| Dataset Name | View Name | Partition | Columns | Primary Keys | Description |",
                "| :--- | :--- | :--- | :---: | :--- | :--- |",
            ]
        )
        for spec in sorted(datasets, key=lambda d: d.name):
            keys_str = ", ".join(f"`{k}`" for k in spec.keys) if spec.keys else "*None*"
            clean_desc = spec.description.replace("|", "\\|").strip()
            lines.append(
                f"| `{spec.name}` | `{spec.view}` | `{spec.partition}` | {len(spec.schema)} | {keys_str} | {clean_desc} |"
            )
        lines.append("")

    # One trailing newline, so the repo's end-of-file-fixer hook never makes the file "stale".
    return "\n".join(lines).rstrip("\n") + "\n"


def main() -> int:
    """Run audit and optionally write or check output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if output is stale")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT, help="Output markdown path")
    args = parser.parse_args()

    content = generate_markdown_report()

    if args.check:
        if not args.output.exists():
            sys.stderr.write(f"Error: {args.output} does not exist\n")
            return 1
        existing = args.output.read_text(encoding="utf-8")
        if existing != content:
            sys.stderr.write(f"Error: {args.output} is stale; run without --check to update\n")
            return 1
        print(f"Master coverage matrix in {args.output} is up to date.")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(f"Wrote master coverage matrix to {args.output} ({len(DATASETS)} datasets cataloged).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
