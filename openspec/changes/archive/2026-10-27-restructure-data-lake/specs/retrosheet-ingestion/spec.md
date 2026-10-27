## MODIFIED Requirements

### Requirement: Retrosheet Storage Layout
Raw event, roster, gamelog and reference files MUST be stored under `raw/retrosheet/<dataset>/[season=YYYY/]`; parsed output under `processed/retrosheet/<dataset>/[season=YYYY/]`. Regular-season and postseason events MUST be separate datasets (`events`, `events_postseason`).
