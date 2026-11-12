# Design: memory-governor

## 1. Evidence (2026-11-12, this machine: 95.7 GB RAM, 8 GB page file)
- 25 workers each parsing a pitch season froze the computer; a Retrosheet run failed with `WinError 1455 paging file
  too small` while 41 GB RAM was free: the commit limit (RAM + page file, 103.7 GB) was 86.5 GB used.
- 32 `multiprocessing` spawn workers whose parent had died held 27.6 GB; after stopping exactly those the commit used
  fell to 58.4 GB.
- The round-trip check crashed with MemoryError on `player_batting_logs` (5.77 M rows) because it built Python lists.

## 2. Prior art and reuse check
`os`/`ctypes` only (`GlobalMemoryStatusEx`, `GetProcessMemoryInfo`, `/proc`), no new dependency; TCP-style slow start
(add one, measure, add another) is the standard way to find a safe concurrency. Reused: the runner's polling loop, the
audit logger, `resolve_concurrency` (kept as the upper bound).

## 3. Decisions
- No fixed job count. Admission: `available - reserve >= measured_growth_per_job * 1.5`, evaluated live on every poll.
- Settling: after a start, wait until two samples of the process memory are within 3 % (or 20 s).
- Pools: one persistent pool, sized once; workers watch their parent (`watch_parent`) and exit when it is gone.
- A probe that cannot read the OS reports plenty, so scheduling never stalls on a broken probe.

## 4. Tests
`tests/test_memguard.py` (12 tests: first job always starts, slow start, admission follows measured growth and live
free memory, reserve is a share of the machine, commit headroom counts, pool size, status sentence, the runner runs side
by side with plenty and one or two at a time when scarce and still finishes, worker exits with parent, pid check, pool
sized once); `tests/test_roundtrip.py`.

## 5. Evidence after the change
Real probes on this machine: 40 GB usable of 96 GB, reserve 14 GB; a pool of 32 requested workers is sized to what fits.
An orphan test (parent killed with `os._exit`): all 3 idle workers left within 8 seconds. Round-trip of
`player_batting_logs`: all 21,999 files and 5,771,788 rows compared, peak working set 4.3 GB, peak commit 6.1 GB, 145 s.
