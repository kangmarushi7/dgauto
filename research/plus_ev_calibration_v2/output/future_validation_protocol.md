# Future validation protocol (Season 3 / untouched season)

## Status

**Season 3 / future-season dataset was not available** at the time of this research run.

True future-season validation is therefore **unavailable**. Within-Season-2 chronological walk-forward is the OOS design used instead.

## Freeze (do not change after Season 3 arrives)

1. Reconstruct `raw_model_probability = (1 + qualifier_pct/100) / odds`.
2. Walk-forward monthly expanding calibration: Platt + isotonic, min_train=200.
3. Fair market probability: only when opposite-side or full mutually exclusive book prices exist; never treat raw `1/odds` as fair.
4. Edge vs fair market when available; else report edge vs raw implied as **proxy only**.
5. Predefined edge thresholds for sensitivity: **1%, 2%, 3%, 5%** — report all; do not pick the best.
6. Fixed probability bins, odds bands, and edge buckets as in v2 code — **no re-optimization**.
7. Flat 1-unit stakes for all ROI/P&L.
8. Evaluate Season 3 **exactly once** after freezing.

## Command

```bash
python3 -m research.plus_ev_calibration_v2.run \
  --input /path/to/season2.csv \
  --future /path/to/season3.csv \
  --out-dir research/plus_ev_calibration_v2/output
```

## Season 3 evaluation steps

1. Fit calibration **only** on Season 2 decided bets (full Season 2 as train).
2. Apply frozen Platt/isotonic models to Season 3 raw probabilities.
3. Compute Brier / log loss / ECE on Season 3.
4. Compute ROI / P&L / edge-bucket tables on Season 3 without changing thresholds.
5. If closing odds exist in Season 3, compute CLV; else state CLV unavailable.
6. Do **not** re-tune after viewing Season 3 metrics.

## Pass / fail framing (descriptive, not automatic deploy)

- Probability: OOS ECE/Brier improvement over raw.
- Edge: monotonic or at least non-inverted edge→ROI relationship OOS.
- Betting: ROI bootstrap CI; deploy only if positive with adequate N and CLV support (if measurable).
