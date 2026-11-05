# Design
- In-memory per extractor (a chunk is one process): the first request probes, later ones skip; 6 threads may probe together once an hour.
- Evidence: test with a fake clock (5 requests, 1 probe; +1 h, 2nd probe; 200 clears; 4 probes in all).
- Not done: a file-based flag (goes stale after a provider fix).
