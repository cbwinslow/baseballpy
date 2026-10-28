# Docs Generation Specification

## Purpose
Generated documentation (column dictionaries, CLI reference) cannot drift from the code, and every description is traceable to its source.

## Requirements

### Requirement: Column Descriptions With Provenance
Every column of every generated dictionary MUST show a description taken from provider metadata or marked `TODO`; each description MUST cite its source (or be flagged `authored`); the described-column count MUST never decrease (ratchet test) and `baseballpy docs coverage` MUST report it per source.
