# Design
Evidence: curl of the seven sport ids returned HTTP 404 with body `Object not found` for seasons 2023 and 2024; sport 1 and 11-23 return 200. Alternatives rejected: dropping the seven sports (data left behind if the provider later fills them); catching HttpStatusError in the adapter (swallowing). The rule is derived from the declaration (`{sport_id}` in path or params).

## As built
The rule lives in `MlbEndpoint.__post_init__` (covers the generated stats endpoints too, which are not built by `_ep`) and applies to sport and team placeholders. Paginated endpoints are excluded: their loop does not handle 404 and none has been observed to fail. A 404 is recorded as an empty part and counted in `EndpointReport.missing`, so it stays visible.
