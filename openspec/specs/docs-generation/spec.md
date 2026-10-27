# Docs Generation Specification

### Requirement: Column Descriptions With Provenance
Every column of every generated dictionary MUST show a description taken from provider metadata or marked `TODO`; each description MUST cite its source (or be flagged `authored`); the described-column count MUST never decrease (ratchet test) and `baseballpy docs coverage` MUST report it per source.
