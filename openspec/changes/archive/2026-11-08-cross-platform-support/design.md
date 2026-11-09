# Design: cross-platform-support

## Decisions
- D1 One rule for text: UTF-8 in, UTF-8 out, LF line endings, on every OS. `write_text(..., encoding="utf-8", newline="\n")` (Python 3.10+, the project needs 3.11). Reads keep the default newline handling, which accepts LF and CRLF.
- D2 `spawn` for worker processes on every OS. It is the Windows and macOS default and the only start method that is safe with threads in the parent; Python 3.14 moves Linux away from `fork` for the same reason (Python docs, "multiprocessing start methods").
- D3 Enforce by reading the source (`ast`), because the failure only shows on the other OS. CI runs on both, but a Windows-only or Linux-only difference in a written byte is easy to miss.
- D4 `.gitattributes` makes checkouts LF everywhere, so generated docs compare equal on every OS.
- D5 No OS scheduler (Task Scheduler, cron, systemd) in the project. Always-on downloading is a Python process (change `download-queue`, B-313).

## Evidence
Web check: Python docs on `multiprocessing` start methods and `Path.write_text(newline=)`; git docs on `text=auto eol=lf`. pybaseball and baseballr have no equivalent concern because they write no files of their own.
Linux: the CI `test` job runs the full suite on `ubuntu-latest` for Python 3.11, 3.12 and 3.13 (last green run recorded in `tasks.md`).
Not verified: macOS (not in the CI matrix), NFS or network shares (`flock` may not work there), and Windows paths longer than 260 characters on machines without long paths enabled.
