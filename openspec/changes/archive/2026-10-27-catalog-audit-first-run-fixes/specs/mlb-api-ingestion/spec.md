## ADDED Requirements

### Requirement: Provider Lists Are the Registry
Every standings type, roster type and game type listed by the provider MUST be present in the registry (and the `GameType` enum MUST equal `/v1/gameTypes`); `baseballpy catalog audit` MUST report any difference as MISSING or STALE.
