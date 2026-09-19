# Arahus Live Candidate V1

**Status:** Frozen forward-validation candidate  
**research_only / paper book:** `log_type=arahus_live_v1`  
**Auto-sync default:** `ARAHUS_LIVE_V1_ENABLED=false` (manual UI sync still works)

## Frozen rules

| Rule | Value |
|------|--------|
| Market | Over 2.5 ONLY |
| Odds | 1.30 ≤ odds ≤ 1.49 inclusive (no rounding) |
| Leagues | All leagues (no whitelist) |
| Confidence | Calculated & logged — **not a gate** |
| BTTS / O3.5 / other markets | Excluded |
| Stake | Existing Arahus v1 ladder (0.75 / 1.0 / 1.5) |
| Manual overrides / chasing / Kelly | None |

Exact qualification:

```text
market == Over 2.5 AND odds is not None AND 1.30 <= odds <= 1.49
```

## Isolation

- Separate from Arahus v1 (`log_type=arahus`) and Arahus v2 (`log_type=arahus_v2`)
- Dedup within Live V1 only: `(fixture_date, fixture, bet_type, team_name)`
- Dashboard/stats never mix with other strategies unless explicitly labelled

## OOS reference (validation history — not a guarantee)

Period: 2026-09-01 → 2026-09-19  
N=62 · PnL=+4.231u · ROI=+7.76%  
See `reports/arahus_oos_v1_2026-09-19.md` when present.

## Config

```python
ARAHUS_LIVE_V1 = {
    "market": "Over 2.5",
    "odds_min": 1.30,
    "odds_max": 1.49,
    "league_whitelist": None,
    "confidence_min": None,
}
```

Env:

- `ARAHUS_LIVE_V1_ENABLED` — include in auto-sync after refresh (default false)
- `ARAHUS_LIVE_V1_ODDS_MIN` / `ARAHUS_LIVE_V1_ODDS_MAX` — frozen band (defaults 1.30 / 1.49)

## Decision log

Every evaluated O2.5 candidate writes `arahus_live_v1_decision_log` with:

`strategy_version`, `signal_timestamp`, `kickoff_timestamp`, `league`,
`home_team`, `away_team`, `market`, `confidence`, `entry_odds`,
`qualification_result`, `rejection_reason`, `stake`, plus nullable
`closing_odds` / `closing_timestamp` / `clv` for future CLV (null until sourced).

Rejection reasons: `market_not_o25`, `missing_odds`, `odds_below_min`,
`odds_above_max`, `invalid_odds`.

## UI

- Engine: `/arahus-live-v1`
- Log: `/arahus-live-v1-bet-log`
- Decisions export: `/api/arahus-live-v1/decisions?format=csv`
