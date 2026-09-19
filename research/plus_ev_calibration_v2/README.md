# Plus EV calibration research v2

**Research only.** Does not modify production +EV filters, sync, staking, Arahus, or DB schemas.

## Goal

Determine whether model probabilities are calibrated, whether walk-forward calibration helps, and whether calibrated probabilities contain information beyond the bookmaker market — **without filter mining**.

## Run

```bash
pip install -r research/plus_ev_calibration_v2/requirements.txt

# Season 2 only (current situation)
python3 -m research.plus_ev_calibration_v2.run \
  --input /path/to/plus_ev_bet_log_season2.csv

# When Season 3 exists (untouched validation — run once after freezing methodology)
python3 -m research.plus_ev_calibration_v2.run \
  --input /path/to/season2.csv \
  --future /path/to/season3.csv
```

## Outputs (`output/`)

| File | Purpose |
|------|---------|
| `plus_ev_calibration_v2_report.md` | Master report |
| `data_audit.md` | Schema / season discovery |
| `leakage_audit.md` | Leakage controls |
| `calibration_report.md` | Probability scores & bins |
| `market_probability_report.md` | Fair market + edge tables |
| `clv_report.md` | CLV (or explicit unavailability) |
| `future_validation_protocol.md` | Frozen Season 3 protocol |
| `results.csv` / `results.json` | Machine-readable OOS rows & aggregates |
| `plots/` | Calibration & edge charts |

## Important limitations (Season 2 export)

- **No closing/opening odds** → CLV cannot be measured.
- **No opposite-side prices** → margin-free fair market probability unavailable; proxy edge vs raw implied is labeled as proxy only.
- **No Season 3 file** → true future-season validation unavailable until provided.
