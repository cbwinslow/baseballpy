# Proposal: memory-governor (concurrency follows live, measured memory)

## Why
On 2026-11-12 an ingest of Statcast pitches ran 25 jobs at once (`-c auto` took the CPU count) and froze the owner's
96 GB computer: each pitch season holds hundreds of thousands of rows in memory. Earlier the same machine reported
"paging file too small" (Windows commit limit) while RAM was free, and 32 orphaned worker processes of a crashed run
kept 27.6 GB committed. The owner asked for diagnostics and a dynamic limit, not a small fixed number.

## What
1. `core/memguard.py::MemoryGovernor`: usable memory is the smaller of free RAM and the OS commit headroom; the reserve
   is a share of the machine (`max(2 GiB, 15 %)`); the growth of the process per running job is measured; a job starts
   only while the free memory above the reserve covers the measured growth with a safety factor, and only after the
   previous job's memory has settled. The first job always starts.
2. The job runner starts jobs through the governor (the worker count is only the upper bound) and audit-logs a
   `memory_hold` record when jobs are held back.
3. The Retrosheet shared process pool is sized once from the memory left, and each worker exits when its parent dies.
4. `baseballpy ingest` announces the memory status and `baseballpy doctor` shows it.
5. The round-trip check compares in Arrow (distinct-value counts), not Python lists: its biggest table went from a
   MemoryError to 4.3 GB peak.
