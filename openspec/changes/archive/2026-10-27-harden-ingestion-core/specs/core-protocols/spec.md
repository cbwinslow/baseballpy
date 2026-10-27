## MODIFIED Requirements

### Requirement: Decoupled Protocol Hierarchy
Extractors, normalizers and sinks MUST structurally satisfy their protocols including method signatures; a contract test MUST verify signatures (not only `isinstance`) for every registered source.
