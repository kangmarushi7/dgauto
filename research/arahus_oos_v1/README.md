# Arahus O2.5 chronological OOS validation

**research_only = true** · **can_place_real_bet = false**

Validates a **frozen** candidate (Over 2.5, odds 1.30–1.49 inclusive).  
Does **not** optimize leagues, odds, confidence, or staking from OOS results.

## Critical finding: no league whitelist

This repository does **not** define a selected-league whitelist for Arahus.
See `config.LEAGUE_WHITELIST_STATUS`. Until one is added in code, the candidate
applies **no league filter** (baselines B and C are identical).

## Chronological split

| Period | Dates |
|--------|-------|
| Development | 2026-07-01 → 2026-08-31 |
| OOS | 2026-09-01 → latest settled bet |

## Run

```bash
python3 -m research.arahus_oos_v1.run \
  --input /path/to/arahus-log.csv

# Optional DB:
export DATABASE_URL='postgresql://...'
python3 -m research.arahus_oos_v1.run --from-db
```

Outputs:

- `research/arahus_oos_v1/output/arahus_oos_v1_YYYY-MM-DD.md`
- `research/arahus_oos_v1/output/arahus_oos_v1_YYYY-MM-DD.json`
- mirrored under `reports/`

## Reuse

| Existing | Use |
|----------|-----|
| `app/arahus_engine.py` / v2 | Market labels, PnL convention, odds band constants (v2) |
| `app/bet_log.compute_bet_stats` | Dashboard reconciliation reference |
| `research/plus_ev_calibration_v2` | Bootstrap / report layout patterns |
| Uploaded Excel/CSV export | Primary historical dataset when DB unreachable |
