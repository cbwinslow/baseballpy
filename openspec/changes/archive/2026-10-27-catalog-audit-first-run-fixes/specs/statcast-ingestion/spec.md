## ADDED Requirements

### Requirement: Verified `unsupported` Verdicts
A Savant route may be recorded as `unsupported` only after the bare route and each documented parameter were tried one at a time; the entry MUST record `verified_on` and `tried`, and the audit MUST re-probe it with default parameters and report REVIVED when it answers.
