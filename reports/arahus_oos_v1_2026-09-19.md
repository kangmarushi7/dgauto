# Arahus O2.5 OOS Validation

_Generated: 2026-09-19T21:05:32.168431+00:00_

**research_only = true** · **can_place_real_bet = false**

## Frozen configuration

- Candidate: `arahus_oos_candidate_v1`
- Market: Over 2.5 only (`over_2_5`)
- Odds range: 1.3 ≤ odds ≤ 1.49 (inclusive, no rounding)
- League whitelist: **undefined in repo** — no league filter applied
- BTTS: False · Over 3.5: False
- Confidence rule: **not used as a gate** (descriptive bands only)
- Stake rule (primary): logged `units` from Arahus log; also flat 1.0u normalized
- Development period: 2026-07-01 → 2026-08-31
- OOS period: 2026-09-01 → 2026-09-19
- Data source: `/home/ubuntu/.cursor/projects/workspace/uploads/arahus-log_e332.csv`

### League whitelist ambiguity

No CURRENT_ARAHUS_SELECTED_LEAGUE_WHITELIST (or equivalent) exists. Arahus v1/v2 do not gate picks by league. Flashscore league aliases in app/flashscore_client.py are settlement matching only, not a pick whitelist. Do not invent a league list from OOS results.

Sources checked: `app/arahus_engine.py`, `app/arahus_v2_engine.py`, `app/flashscore_client.py (settlement aliases only)`, `rules.json`, `research/`

## Push / PnL convention

- Won: `(odds − 1) × units`
- Lost: `−units`
- Push: PnL = 0; stake **included** in total staked
- Open bets: excluded from settled ROI

## Main result (OOS, logged stake)

| Metric | OOS |
|--------|-----|
| Bets | 62 (larger sample) |
| W-L-P | 47-14-1 |
| Win% | 77.05% |
| Avg Odds | 1.405 |
| Median Odds | 1.400 |
| Staked | 54.500 |
| PnL | 4.231 |
| ROI | 7.76% |
| Avg PnL / bet | 0.0682 |
| Max Drawdown (u) | 2.890 |
| Max Drawdown % | 227.27% |
| Longest Losing Streak | 2 |
| Longest Winning Streak | 11 |
| Worst loss / Best win | -1.500 / 0.540 |
| Profit Factor | 1.345 |
| Std (per-bet PnL) | 0.5284 |
| Sharpe-like (mean/std, not annualized) | 0.129 |
| Bootstrap 95% CI ROI | [-7.75%, 22.32%] (seed=42, n_boot=2000) |
| Bootstrap 95% CI mean PnL/bet | [-0.0677, 0.1962] |

### Flat 1.0u normalized (same OOS bets)

N=62 · PnL=4.980 · ROI=8.03% · MaxDD=3.520

## Baseline comparison (same OOS window)

| Strategy | Bets | Win% | Avg Odds | Staked | PnL | ROI | Max DD |
|----------|------|------|----------|--------|-----|-----|--------|
| All Arahus O2.5 | 107 | 69.81% | 1.439 | 92.75 | -0.501 | -0.54% | 3.609 |
| O2.5 + selected leagues + odds 1.30–1.49 | 62 | 77.05% | 1.405 | 54.50 | 4.231 | 7.76% | 2.890 |
| O2.5 + odds 1.30–1.49 (no league filter) | 62 | 77.05% | 1.405 | 54.50 | 4.231 | 7.76% | 2.890 |

Note: Strategies B and C are identical because no league whitelist is defined in the repository.

## League results (OOS candidate)

| League | Bets | W-L-P | Win% | Avg Odds | Staked | PnL | ROI | Max DD | Sample |
|--------|------|-------|------|----------|--------|-----|-----|--------|--------|
| Super League | 12 | 10-2-0 | 83.33% | 1.406 | 10.75 | 2.103 | 19.56% | 1.005 | small sample |
| Eerste Divisie | 10 | 7-3-0 | 70.00% | 1.392 | 9.00 | -0.940 | -10.44% | 3.250 | small sample |
| Eredivisie | 10 | 9-1-0 | 90.00% | 1.394 | 8.75 | 2.000 | 22.86% | 1.000 | small sample |
| Major League Soccer | 10 | 7-2-1 | 77.78% | 1.400 | 8.50 | 0.650 | 7.65% | 1.750 | small sample |
| Bundesliga | 6 | 5-1-0 | 83.33% | 1.407 | 5.25 | 1.050 | 20.00% | 0.750 | very small sample |
| 2. Bundesliga | 4 | 3-1-0 | 75.00% | 1.410 | 4.50 | 0.690 | 15.33% | 0.750 | very small sample |
| Pro League | 2 | 1-1-0 | 50.00% | 1.420 | 1.50 | -0.420 | -28.00% | 0.750 | very small sample |
| UEFA Champions League | 2 | 1-1-0 | 50.00% | 1.440 | 1.75 | -0.670 | -38.29% | 1.000 | very small sample |
| Eliteserien | 1 | 0-1-0 | 0.00% | 1.440 | 0.75 | -0.750 | -100.00% | 0.000 | very small sample |
| La Liga | 1 | 1-0-0 | 100.00% | 1.330 | 0.75 | 0.248 | 33.07% | 0.000 | very small sample |
| League Cup | 1 | 1-0-0 | 100.00% | 1.480 | 0.75 | 0.360 | 48.00% | 0.000 | very small sample |
| Ligue 1 | 1 | 1-0-0 | 100.00% | 1.440 | 0.75 | 0.330 | 44.00% | 0.000 | very small sample |
| Superliga | 1 | 0-1-0 | 0.00% | 1.440 | 0.75 | -0.750 | -100.00% | 0.000 | very small sample |
| Süper Lig | 1 | 1-0-0 | 100.00% | 1.440 | 0.75 | 0.330 | 44.00% | 0.000 | very small sample |

### Non-selected leagues

No CURRENT_ARAHUS_SELECTED_LEAGUE_WHITELIST (or equivalent) exists. Arahus v1/v2 do not gate picks by league. Flashscore league aliases in app/flashscore_client.py are settlement matching only, not a pick whitelist. Do not invent a league list from OOS results.

## Odds-band breakdown (analysis only — do not retune)

| Band | Bets | W-L-P | Win% | PnL | ROI |
|------|------|-------|------|-----|-----|
| 1.30–1.34 | 9 | 7-2-0 | 77.78% | -0.279 | -2.94% |
| 1.35–1.39 | 12 | 11-1-0 | 91.67% | 3.320 | 25.54% |
| 1.40–1.44 | 32 | 21-10-1 | 67.74% | -1.180 | -4.77% |
| 1.45–1.49 | 9 | 8-1-0 | 88.89% | 2.370 | 32.69% |

## Confidence-band breakdown (analysis only — do not retune)

| Band | Bets | W-L-P | Win% | PnL | ROI |
|------|------|-------|------|-----|-----|
| 60–64 | 16 | 12-4-0 | 75.00% | 1.020 | 8.50% |
| 65–69 | 31 | 22-8-1 | 73.33% | 0.226 | 0.90% |
| 70–74 | 4 | 4-0-0 | 100.00% | 1.600 | 40.00% |
| 75–79 | 7 | 6-1-0 | 85.71% | 1.310 | 17.47% |
| 80+ | 4 | 3-1-0 | 75.00% | 0.075 | 1.25% |

## Time-series stability

### By week

| Week | Bets | Win% | PnL | ROI |
|------|------|------|-----|-----|
| 2026-W36 | 21 | 75.00% | 1.085 | 6.20% |
| 2026-W37 | 25 | 76.00% | 0.808 | 3.48% |
| 2026-W38 | 16 | 81.25% | 2.338 | 17.00% |

Rolling 25 (last window ending 2026-09-19): ROI=11.41%, PnL=2.596, Win%=80.00% · windows=38

Rolling 50 (last window ending 2026-09-19): ROI=5.29%, PnL=2.326, Win%=75.51% · windows=13

## CLV

CLV unavailable in current dataset.

## Reconciliation vs full-log summary

| | Existing-style | Calculated |
|-|----------------|------------|
| Bets | 339 | settled 333 (open 6) |
| Won | 237 | 237 |
| Lost | 93 | 93 |
| Push | 3 | 3 |
| PnL | logged 15.468 | recomputed 15.458 |
| Match | | True (delta=0.01) |

## Data-quality issues

- **missing_odds**: count=5 — excluded_from_candidate
- **open_or_missing_result**: count=6 — excluded_from_settled_roi
- **no_created_at_in_excel_export**: count=339 — cannot verify bet-after-kickoff; fixture_date used as chronological key
- **no_closing_odds_in_dataset**: count=339 — CLV unavailable

## Leakage audit

No intentional look-ahead into OOS for parameter selection. Configuration was fixed prior to September evaluation. Qualification does not use status/pnl/closing odds.

- Excel export has no created_at — cannot prove bet was placed before kickoff.
- No closing odds — CLV not measurable.
- Multiple markets per fixture historically in v1 log; candidate keeps O2.5 only.
- League whitelist absent — cannot test league-filter value-add until defined.

## Future sample size (rough)

N required for SE≈0.05 on mean per-bet return: **112** (σ=0.5284). N ≈ (σ/SE)^2 for mean per-bet return; not a power calculation for ROI>0

## Conclusion (factual only — no go/no-go verdict)

- OOS ROI was positive (7.76%).
- Sample size: N=62 (larger sample).
- Bootstrap 95% CI for portfolio ROI: [-7.75%, 22.32%].
- Max drawdown: 2.890u (227.27%).
- Stability: see weekly / rolling tables; last rolling-25 ROI=11.41%.
- League filtering: **could not be tested** — whitelist undefined; B ≡ C.
- CLV: CLV unavailable in current dataset..
- Leakage into OOS selection: **not detected** for parameter choice; see residual limitations.

### Objective conditions before considering live (checklist, not a verdict)

1. Define and freeze an explicit league whitelist in code (or formally document none).
2. Accumulate larger OOS N (see future sample size note) without retuning.
3. Capture closing odds at sync for CLV.
4. Persist `created_at` alongside exports to prove pre-kickoff placement.
5. Keep odds band / market / confidence gates frozen; do not optimize on this OOS window.
