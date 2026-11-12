# Design: fast-view-sync

## 1. Evidence
Timed on the real lake (176,897 files, 271 views): the refresh took about 35 minutes before the change (two runs,
2026-11-11); after it the first run took 256 seconds (it builds the cache, 16 footers at once) and the second 116
seconds (listing the files and creating the views). Listing the files alone takes about 35 seconds.

## 2. Prior art and reuse check
A cache keyed by size and modification time is the standard way build tools skip unchanged files; nothing in the
project cached footers. The cache is a plain JSON file written atomically; a failure to write only costs a re-read.

## 3. Decisions
- The cache key is the relative path plus size and mtime (nanoseconds): a rewritten file is read again.
- A missing or unreadable cache is an empty cache; the answer never depends on it (same rows either way).

## 4. Tests
`tests/test_database.py::test_the_inventory_reads_a_file_footer_only_when_the_file_is_new_or_changed`.

## 5. Remaining cost
The 116 seconds of a second run are file listing and view creation over 177k small files; fewer, larger files (the
segment rebuild, B-375 to B-380) is the cure.
