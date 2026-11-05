# Tolerant box-account cells

## Why
The first all-history Retrosheet run (2026-11-05) failed 22 of 157 seasons (1904, 1913, 1921-1947 in part): old box accounts hold cells such as `2i`, `NA`, blank numbers, upper-case `FALSE` and a blank integer info value, and the strict parser rejected the whole season.

## What changes
Value-level problems become NULL plus a quarantine entry (the project's rule for uncastable cells); `FALSE`/`TRUE` in any case are valid flags; blank values are no value. Layout problems (field counts, a record before any id) still raise.
