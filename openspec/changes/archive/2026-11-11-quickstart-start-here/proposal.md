# Proposal: a "Start here" section in the existing quickstart

## Why

The quickstart (`docs/QUICKSTART.md`) opens with a two-door reading guide and then a long catalog of every
dataset. A new user (the owner's goal: an easy, uniform tool other people can use) has no five-step path from
install to first query, and no first command per source. The owner asked for no new documents: this adds one
section to the existing page.

## What

- A "Start here" section at the top of `docs/QUICKSTART.md`: five steps (install, see what a command would
  download with `--dry-run`, download, see what you hold, use it as a DataFrame, in SQL or export it) and a
  table with the first command for each core source (Statcast, Retrosheet, Chadwick, Lahman, MLB API). Every
  command was run as `--dry-run` on an empty home on 2026-11-11 and gave a valid plan.
- A test that keeps it true: every `baseballpy <command>` shown in that section names a real CLI command, and
  every `ingest <source>` names a registered adapter.
- One requirement in the `agent-runbooks` spec (the docs have a checked entry point), no ADR needed (no
  decision beyond the owner's "no new documents").

## Out of scope

Rewriting the dataset catalog below the section; new documents.
