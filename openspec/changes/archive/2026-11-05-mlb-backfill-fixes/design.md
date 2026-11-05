# Design
- Measured: one save of a 3,000-entry manifest took 50 ms with `indent=2` and 27 ms without (the C encoder); 30 threads x 8 saves took 102 s and failed before, 7.7 s and passed after.
- The lock timeout stays a safety net (30 s, holders keep it about 30 ms); the cause was save cost, not the timeout.
- Not changed: one manifest per dataset (a per-season manifest would change the lake layout).
