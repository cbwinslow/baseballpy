## MODIFIED Requirements

### Requirement: Lahman Storage Layout
Raw CSVs MUST be stored at `raw/lahman/<Table>/<Table>.csv` and typed Parquet at `processed/lahman/<Table>/data.parquet`; each table is a separate dataset with view `lahman_<table_lower>`.
