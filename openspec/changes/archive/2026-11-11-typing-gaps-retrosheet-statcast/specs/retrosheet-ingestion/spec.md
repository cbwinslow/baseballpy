## ADDED Requirements

### Requirement: Text Columns Hold No Typed Data Without A Recorded Reason
A column typed text MUST NOT hold only whole numbers, decimals or dates unless the reason is recorded; the lake audit
MUST find such columns (leading zeros and mixed text stay text), and Retrosheet daily split dates MUST be `date32`
and the box score tiebreaker `int16`.

#### Scenario: The audit finds typed text
- **WHEN** a view has text columns of whole numbers, decimals, packed dates, ISO dates, zero-padded line scores and mixed text
- **THEN** the audit reports the numbers, decimals and dates and leaves the line scores and mixed text alone
- Verified by `tests/test_typing_audit.py::test_text_columns_that_hold_only_numbers_or_dates_are_found`.

#### Scenario: Daily split dates and tiebreaker are typed
- **WHEN** a daily split row and a box score row are parsed
- **THEN** the dates are `date32` values and the tiebreaker is an integer
- Verified by `tests/test_retrosheet.py::test_parse_daily_splits` and `tests/test_retrosheet_box.py::test_the_tiebreaker_is_a_number_not_text`.
