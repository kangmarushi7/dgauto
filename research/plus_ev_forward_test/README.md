# Plus EV forward-test / paper-test framework

**research_only = true**  
**can_place_real_bet = false**

This module does **not** modify production +EV filters, Arahus, staking, sync, or production DB behavior.

## Purpose

Prospectively (and retrospectively for existing +EV log data) evaluate four **fixed** paper portfolios independently:

| Portfolio | Rule |
|-----------|------|
| 1 — Odds 2.10–2.50 | Every qualifying bet with odds in [2.10, 2.50]. No market restriction. |
| 2 — DC X2 | Every qualifying Double Chance X2. No extra optimization. |
| 3 — Over 3.5 | Every qualifying O3.5 (benchmark/control). |
| 4 — Over 2.5 | Every qualifying O2.5 (benchmark/control). |

Do **not** combine filters. Do **not** retune after seeing results.

## Commands

```bash
pip install -r research/plus_ev_forward_test/requirements.txt
# Also need app DB deps for --from-db via Postgres:
#   pip install sqlalchemy 'psycopg[binary]'

# From VPS (preferred): Postgres DATABASE_URL, else live app HTTP API
export DATABASE_URL='postgresql://...'           # Railway/VPS Postgres
# OR when app is up and DATABASE_URL unavailable here:
export APP_BASE_URL='https://dgauto-production.up.railway.app'

python3 -m research.plus_ev_forward_test.run run-all --from-db --season 2

# Force one path:
python3 -m research.plus_ev_forward_test.run seed-db --season 2 --prefer db
python3 -m research.plus_ev_forward_test.run seed-db --season 2 --prefer api

# From Season 2 CSV export (fallback when VPS unreachable)
python3 -m research.plus_ev_forward_test.run run-all \
  --input /path/to/plus_ev_bet_log_season2.csv
```

## Suggested external cron (research only)

Do **not** enable inside production scheduler by default. Point an external cron at:

```bash
python3 -m research.plus_ev_forward_test.run collect
python3 -m research.plus_ev_forward_test.run snapshot-closing
python3 -m research.plus_ev_forward_test.run settle
python3 -m research.plus_ev_forward_test.run report
```

## Data

- Ledger: `research/plus_ev_forward_test/data/signals.jsonl`
- Odds snapshots: `research/plus_ev_forward_test/data/odds_snapshots.jsonl`
- Reports: `research/plus_ev_forward_test/output/`

## CLV methodology

When `closing_odds` exists:

- `bet_implied = 1 / odds_at_signal`
- `close_implied = 1 / closing_odds`
- `clv = close_implied - bet_implied` (>0 = longer price than close / beat the close)

Season 2 CSV seed has **no closing odds** → CLV cannot be measured for those rows.

## Fair probability

Only when mutually exclusive outcome odds are present (de-vig). Otherwise `fair_probability = null`. Never substitute raw `1/odds` as fair.

## Sample milestones

| N | Interpretation |
|---|----------------|
| <25 | preliminary only |
| 25–49 | very weak |
| 50–99 | interesting |
| 100–249 | meaningful |
| 250–499 | strong building |
| ≥500 | strong forward-test sample |

## Status labels

`INSUFFICIENT SAMPLE` · `PROMISING — NEEDS MORE DATA` · `MIXED` · `NEGATIVE` · `STRONGER EVIDENCE — CONTINUE VALIDATION`

Never: BEST / WINNER / PROVEN PROFITABLE from small N.
