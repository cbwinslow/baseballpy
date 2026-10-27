# Design: Column Descriptions

- **Storage:** one YAML per source; keys are `<dataset>.<column>`; each entry has `text` and `source` (URL or document name) so provenance is auditable. Generated modules are untouched.
- **Sources of truth, in order:** (1) the API itself (`/v1/baseballStats` returns name, group and lookup parameter per statistic), (2) the provider's published format documents, (3) none: leave `TODO`. Anything written by us is flagged `authored: true` and reviewed.
- **Merge rule:** the docs generator reads the YAML and fills the Description column; `TODO` rows are counted per dataset; the ratchet test fails if the count of described columns drops or a new column appears without an entry in sources that are fully described.
- **Scale:** flattened MLB columns derive their meaning from dotted upstream keys (`pitch_data_breaks_spin_rate` = `pitchData.breaks.spinRate`); the generator can inherit a description from the upstream path when the API metadata names it.
- **Risk:** copyright - only short factual definitions with a citation are stored; large documents are linked, not copied.
