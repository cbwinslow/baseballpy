# Retrosheet Endpoint & Dataset Catalog

## Upstream Overview
- **Provider:** Retrosheet (`retrosheet.org`) & Chadwick Baseball Bureau GitHub Mirror
- **Primary Extraction Source:** Fastly-backed GitHub raw mirror (`https://raw.githubusercontent.com/chadwickbureau/retrosheet/master/`)
- **Rate Limit Policy:** Max 15 requests/second
- **Anti-Scraping Policy:** `retrosheet.org` drops TCP SYN connections on automated bulk queries; all bulk historical extractions route exclusively through GitHub mirrors (ADR 1 & ADR 5).

---

## Datasets Covered

### 1. Play-by-Play Event Data (`.EVA` / `.EVN`)
- Extracted per season and league (`A` = American League, `N` = National League).
- Parsed via `chadwickpy` into discrete plate appearance events, pitch sequences, pickoffs, stolen bases, substitutions, and comments.

### 2. Historical Game Logs (1871–present)
- Stored as `gl{YYYY}.txt` containing 161 standard columns:
  - Game dates, line scores, runs, hits, errors, left on base.
  - Starting pitchers, winning and losing pitchers, saves.
  - Umpires (home, 1B, 2B, 3B, LF, RF).
  - Attendance, game duration in minutes, day/night flag.

### 3. Rosters (`.ROS`)
- Annual team rosters mapping 8-character player codes to names, bats/throws handedness, and primary fielding positions.

### 4. Biographical & Ballpark Directories
- `biofile` / `people`: Player biographical records.
- `parks`: Ballpark identifiers, historical team occupancy dates, park names, and cities.
- `schedules`: Scheduled season dates, game times, and postponed contest records.
