# Sean Lahman Baseball Database Catalog

## Upstream Overview
- **Provider:** Sean Lahman / Baseball-Databank
- **Primary Archive Sources:**
  - Annual CSV Zip Archives
  - SQLite Database distribution
- **Coverage:** Complete historical season statistics (1871–present).

---

## Core Tables & Schemas

| Table Name | Description | Primary Key |
| :--- | :--- | :--- |
| `People` | Player master biographical records | `playerID` |
| `Batting` | Annual season-level batting records (H, 2B, 3B, HR, RBI, SB, BB, SO) | `(playerID, yearID, stint)` |
| `Pitching` | Annual season-level pitching records (W, L, G, GS, CG, SHO, SV, IPouts, H, ER, HR, BB, SO) | `(playerID, yearID, stint)` |
| `Fielding` | Annual fielding statistics by position (PO, A, E, DP, PB) | `(playerID, yearID, stint, POS)` |
| `Teams` | Team franchise season records (W, L, R, RA, attendance, park name) | `(yearID, teamID)` |
| `HomeGames` | Historical home game dates and attendance by park | `(yearID, teamID, parkID)` |
| `Parks` | Historical ballpark directory | `parkID` |
| `HallOfFame` | Hall of Fame voting ballots and inductee results | `(playerID, yearid, votedBy)` |
| `AllstarFull` | All-Star Game roster appearances and game IDs | `(playerID, gameID)` |
| `Salaries` | Historical player contract salaries (1985–present) | `(yearID, teamID, playerID)` |
