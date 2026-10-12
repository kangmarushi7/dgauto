# Trade Picks cross-strategy Over 2.5 dedupe

## Goal

When Main and Arahus both qualify the same fixture/day for Over 2.5 on Trade Picks, stake once: **prefer Arahus**, drop Main from the capital surface.

## Scope

- `app/trade_picks.py` after existing Main scenario twin dedupe.
- Applies to UI payload, CSV export path via payload, and bot/WS feed (uses same payload).
- Does **not** delete Main bet-log rows.
- Over 2.5 only; other markets unchanged.

## Rule

Key: `(fixture, kickoff day, market == Over 2.5)`.  
If both Main (`Main_filtered`) and Arahus (`Arahus_filtered`) present → keep Arahus.

## Precedence

User-approved: prefer Arahus.
