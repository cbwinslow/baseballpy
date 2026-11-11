## ADDED Requirements

### Requirement: The Constitution Defines The Final Product Per Source
`openspec/project.md` MUST contain a section "The Final Product" with one row per registered source (what is
downloaded, whether it is reproducible by a pinned ref or by kept raw, the target and current layout, the first
command, and the test that proves it) and the definition of done for the whole product. Every first command shown
MUST name a registered source.

#### Scenario: The table cannot drift from the registry
- **WHEN** a source is registered or a first command is changed
- **THEN** the test suite fails until the constitution's table lists the source and every first command names a registered source
- Verified by `tests/test_final_product.py::test_the_constitution_has_one_row_per_registered_source` and `tests/test_final_product.py::test_every_first_command_names_a_registered_source`.
