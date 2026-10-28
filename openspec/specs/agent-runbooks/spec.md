# Agent Runbooks Specification

## Purpose
Keeps autonomous runs repeatable: one versioned prompt states the contract, the verification and the recording rules.

## Requirements

### Requirement: Versioned Goal-Seek Prompt
The repository MUST contain a deployable goal-seek prompt that requires reading the contract files first, opening an OpenSpec change before editing, verifying with the gates and live evidence, auditing for data left behind and for unverified `unsupported` verdicts, recording tasks/ADRs/specs, committing per section without pushing, and using cited web research for facts the repository cannot answer.
