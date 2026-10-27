## ADDED Requirements

### Requirement: Parameterized Stat Types
Every stat type listed by `/v1/statTypes` MUST either have registered stat combinations (including those that need `sitCodes`, `metrics` or an opposing id) or an `unsupported` entry recording the parameters tried and the verification date; `baseballpy catalog audit` MUST report any other stat type.
