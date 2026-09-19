# Plus EV calibration research (Season 2)

**Research only** — does not modify production filters, sync, or live strategy code.

## Setup

```bash
pip install -r research/plus_ev_calibration/requirements.txt
```

## Run

```bash
python3 -m research.plus_ev_calibration.backtest \
  --input /path/to/plus_ev_bet_log_season2.csv \
  --out-dir research/plus_ev_calibration/output
```

## Outputs

- `plus_ev_calibration_report.md` — full narrative report
- `plus_ev_calibration_results.csv` — per-bet walk-forward probabilities (settled)
- `plus_ev_calibration_results.json` — machine-readable aggregates

## Method notes

- EV is read from `qualifier_pct` (percentage points, e.g. `10.2` → 10.2% edge).
- `raw_model_probability = (1 + EV_decimal) / odds`.
- Calibration (isotonic / Platt) is fit on **prior** bets only (50/50 split + expanding walk-forward).
