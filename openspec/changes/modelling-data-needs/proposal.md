# Modelling data needs (game winners first)

## Why
The owner wants a full, careful prediction system (Marcel, RE24, PECOTA/ZiPS-style projections, team strength, an ensemble game model) to compare with Kalshi and Polymarket prices. Before any model code, every field the models need must be either downloaded, coded for download, or written down as missing with a plan. Starting target: MLB game winners. Totals, props and season markets come later; the field list is built so they can be added without re-downloading.

## What changes
This change adds no code yet. It records, field by field, what the models need, where it comes from, whether we have it, and whether it is safe to use in a backtest ("as of": known before first pitch, never after). It lists the missing sources and the tasks to line them up. Each missing source becomes its own small change later.
