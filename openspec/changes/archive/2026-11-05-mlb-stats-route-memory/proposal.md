# MLB stats route memory

## Why
The 2008-2012 run asked `/v1/stats` 3,399 times and got HTTP 406 every time (5% of requests), then fetched the same data by the people route. Owner: deprecate the refused route.

## What changes
The extractor remembers a 406 for one hour and goes straight to the people route; one request retests after the hour; a 200 clears it. Not marked `unsupported` (ADR 68).
