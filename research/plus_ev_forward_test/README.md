# Plus EV forward-test / paper-test framework

**research_only = true**  
**can_place_real_bet = false**

This module does **not** modify production +EV filters, Arahus, staking, sync, or production DB behavior.

## Purpose

Prospectively (and retrospectively for Season 2 seed) evaluate four **fixed** hypotheses independently:

| Portfolio | Hypothesis |
|-----------|------------|
| A — O3.5 | H1 Over 3.5 repeatable |
| B — O2.5 | H2 Over 2.5 repeatable |
| C — Serie A | H3 Serie A model performance |
| D — Odds 2.10–2.50 | H4 Odds band model performance |

Do **not** combine filters. Do **not** retune after seeing results.

## Commands

```bash
pip install -r research/plus_ev_forward_test/requirements.txt

# Seed Season 2 historical ledger (CLV/fair market unavailable on seed)
python3 -m research.plus_ev_forward_test.run seed-season2 \
  --input /path/to/plus_ev_bet_log_season2.csv

# Generate report
python3 -m research.plus_ev_forward_test.run report

# Or one-shot seed + report
python3 -m research.plus_ev_forward_test.run run-all \
  --input /path/to/plus_ev_bet_log_season2.csv

# Live forward collection (requires app state available; never places bets)
python3 -m research.plus_ev_forward_test.run collect
python3 -m research.plus_ev_forward_test.run snapshot-closing
python3 -m research.plus_ev_forward_test.run settle
python3 -m research.plus_ev_forward_test.run report
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
- `clv = bet_implied - close_implied` (>0 = better price than close)

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
