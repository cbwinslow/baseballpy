## MODIFIED Requirements

### Requirement: Revalidation
The register cache MUST be revalidated against the upstream SHA at least every 24 hours; SHA lookup failures MUST be logged and surfaced, never silently ignored.

### Requirement: Discovery and Completeness
Shard and auxiliary files MUST be discovered from the repository tree; a missing shard is a hard error; unknown columns are preserved in `_extras`.
