# Leakage audit — Plus EV calibration v2

Generated: 2026-09-19T04:47:08.564457+00:00

## Scope

Research-only analysis of logged +EV bets. No production filters, sync, staking, or DB schemas modified.

## When information is known

| Field | Timing in production | Used in research |
|-------|----------------------|------------------|
| Model EV (`qualifier_pct`) | Captured at bet sync / pick time from contemporaneous DG snapshot | Reconstructs `raw_model_probability` |
| Bet odds | Captured at sync time | Used as price / stake EV |
| Outcome / status | Known only after match settlement | Used for evaluation & calibration **training labels** only on prior folds |
| Closing / opening odds | **Not present in Season 2 CSV** | N/A |

## Calibration leakage controls

- Walk-forward expanding window: each monthly test fold trains Platt/isotonic **only** on bets with earlier months.
- Minimum train size: 200 decided bets before emitting calibrated probabilities.
- No full-sample fit evaluated on the same rows for deployment claims.
- Outcomes enter calibration **only** as training labels for past folds.

## Cross-contamination risks

1. **Multiple markets per fixture** — same fixture can appear in several bet rows. Markets share match randomness. We do **not** split by fixture into train/test; chronological fold splitting can still place related markets across nearby times. Documented residual dependence; not removed (would shrink N heavily).
2. **No fixture_id** in Season 2 export — cannot hard-block same-fixture leakage across markets.
3. **Duplicate bet ids** — counted in data audit (`duplicate_ids=0`).
4. **Reconstructed model probability** — derived from logged EV and odds; does not use future outcomes. Formula: `(1 + EV_decimal) / odds`.
5. **Fair market probability** — opposite prices absent; we do **not** fabricate fair probs from single prices (would falsely claim de-vig).

## Post-match information

Settlement (`resolved_at`, `status`, `pnl_units`) is used only after chronological cutoffs for evaluation or as past labels. It is never used to form the raw/calibrated probability for a contemporaneous test bet.

## Verdict

No intentional look-ahead in calibration folds. Residual cluster dependence across markets on the same fixture remains a **documented limitation**, not a silent exploit.
