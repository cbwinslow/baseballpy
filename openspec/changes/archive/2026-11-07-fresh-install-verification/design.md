# Design

- **Evidence:** the clean install lives outside the repository (empty venv, empty `BASEBALLPY_HOME`, working folder elsewhere, `python -I`), so nothing from the developer checkout leaks in. The developer catalog opened with DuckDB 1.5.6 fails with `IOException`: file version 69, readable 64 to 68.
- **Why rebuild is safe:** the catalog database holds views over `processed/` and no data (`database.py`), so moving the file aside to `baseball.duckdb.newer-duckdb` loses nothing. A file at a path the caller chose is never touched; the caller gets an error that says what to do.
- **Not done:** a version ceiling for DuckDB was not added; both 1.5.x and 2.0 now work on the same lake.
