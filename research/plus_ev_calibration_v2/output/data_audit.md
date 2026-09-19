# Data audit — Plus EV calibration v2

## Source
- Path: `/home/ubuntu/.cursor/projects/workspace/uploads/plus_ev_bet_log_season2_39ab.csv`
- Rows: **1900**
- Settled / open: **1755** / **145**
- W / L / Push: **980** / **766** / **9**
- Duplicate ids: **0**
- Fixture date range: `2026-07-03 17:00:00+00:00` → `2026-09-20 03:15:00+00:00`

## Schema / column mapping

```json
{
  "raw_columns": [
    "id",
    "created_at",
    "fixture_date",
    "fixture",
    "league_name",
    "bet_type",
    "category",
    "market",
    "team_name",
    "qualifier_pct",
    "odds",
    "units",
    "status",
    "pnl_units",
    "resolved_at"
  ],
  "resolved_mapping": {
    "id": "id",
    "created_at": "created_at",
    "fixture_date": "fixture_date",
    "fixture": "fixture",
    "league": "league_name",
    "bet_type": "bet_type",
    "category": "category",
    "market": "market",
    "team": "team_name",
    "ev_raw": "qualifier_pct",
    "odds": "odds",
    "units": "units",
    "status": "status",
    "pnl": "pnl_units",
    "resolved_at": "resolved_at",
    "closing_odds": null,
    "opening_odds": null,
    "fixture_id": null,
    "bookmaker": null,
    "model_prob": null,
    "opposite_odds": null
  }
}
```

## Odds snapshots

- Opening odds present: **False**
- Closing odds present: **False**
- Opposite-side odds present: **False**
- Fixture IDs present: **False**

**CLV status:** CLV cannot currently be measured from this dataset.

## Season discovery

- App seasons: Season 1 (through 2026-06-30 IST), Season 2 (from 2026-07-01).
- **Season 3 / future season dataset: not found** in repo or uploads.
- Only Season 2 +EV bet log CSV was available for this run.

## Notes

- Logged EV lives in `qualifier_pct` (percentage points).
- Model probability is reconstructed as `(1 + EV_decimal) / odds`.
- No production DB schemas were modified.
