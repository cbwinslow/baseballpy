# Tasks: retrosheet-site-files

- [x] 1.1 Tests first: `tests/test_retrosheet_site.py` (robots paths never requested; a throttle answer stops the run;
  files stored once and skipped on a rerun; paced and honestly identified client; audit events). Done when they fail
  for the missing module.
- [x] 1.2 `sources/retrosheet/site.py` (file table, `site_client`, `fetch_site_files`, `probe_sizes`) and
  `scripts/fetch_retrosheet_site.py`. Done when 1.1 passes.
- [x] 1.3 Run it for real, stage by stage (core, bundles after a size probe, discrepancies, official totals), the
  result (files, bytes, seconds, any refusal) recorded in `design.md`. Done when every group ran or stopped with a reason.
- [x] 1.4 Compare the files with what we hold and with the live GitHub mirror, list what is new, propose what to
  codify (a follow-up change); spec requirement, ADR, gates, archive.
