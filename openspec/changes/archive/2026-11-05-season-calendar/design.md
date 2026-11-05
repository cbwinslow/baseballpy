# Design

- Web check: the MLB calendar lists 2027 (spring training 2027-02-19) in November 2026, so "listed" is not "started"; the start date decides.
- Only the current year needs the calendar: earlier years always started, later years never did.
- The calendar is injectable (`calendar=`) so adapter tests do not touch the clock or the network.
- A calendar that cannot be read raises (no silent clock fallback).
- Retrosheet is not changed: its season list comes from the provider's own file listing (2026 listed with only a schedule completed without error in the 2026-11-05 backfill).
- Rejected: a hard-coded month (brittle); trusting the provider listing for MLB/Statcast (lists next year early).

## Evidence
- Live calendar at four pretend dates: 2026-11-05 latest 2026 (2027 in the future); 2027-01-15 latest 2026 (2027 not started, first day 2027-02-19); 2027-02-19 and 2027-03-26 latest 2027; 2026 finished.
- Not verified: what Savant leaderboards or each MLB endpoint return for a not-started season (they are now never asked).
