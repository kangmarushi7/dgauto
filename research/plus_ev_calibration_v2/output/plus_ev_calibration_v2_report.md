# Plus EV calibration v2 — master report

_Generated: 2026-09-19T04:47:09.144142+00:00_

## 1. Executive summary

Season 2 analysis only. Settled baseline ROI=-0.0520. Walk-forward OOS ROI=-0.0927 on 680 bets (OOS months after warm-up: 2026-09; 95% CI -0.1574–-0.0276). Calibration improves OOS Brier/ECE (raw→Platt). **Fair-market edge unmeasurable** without opposite prices. **CLV cannot currently be measured from this dataset.** **No deployable edge established yet.**

## 2. Dataset and data quality

```json
{
  "source_path": "/home/ubuntu/.cursor/projects/workspace/uploads/plus_ev_bet_log_season2_39ab.csv",
  "total_rows": 1900,
  "settled": 1755,
  "wins": 980,
  "losses": 766,
  "pushes": 9,
  "open": 145,
  "duplicate_ids": 0,
  "has_closing_odds": false,
  "has_opening_odds": false,
  "has_opposite_odds": false,
  "has_fixture_id": false,
  "fixture_date_range": [
    "2026-07-03 17:00:00+00:00",
    "2026-09-20 03:15:00+00:00"
  ],
  "clv_status": "CLV cannot currently be measured from this dataset."
}
```

See `data_audit.md` for full schema dictionary.

## 3. Leakage audit

See `leakage_audit.md`. Walk-forward monthly folds; residual same-fixture multi-market dependence documented.

## 4–6. Raw / Platt / Isotonic calibration

```json
{
  "raw": {
    "n": 680,
    "brier": 0.25723542473293,
    "log_loss": 0.7132206021931008,
    "ece": 0.12202160926813715,
    "calibration_slope": 0.6218294172453657,
    "calibration_intercept": -0.2870520443148022
  },
  "platt": {
    "n": 680,
    "brier": 0.2440078184335753,
    "log_loss": 0.6809568857446843,
    "ece": 0.0438721240839549,
    "calibration_slope": 0.8371725106460367,
    "calibration_intercept": -0.13322607160156005
  },
  "isotonic": {
    "n": 680,
    "brier": 0.2442330990749389,
    "log_loss": 0.6818773129798696,
    "ece": 0.04313878070185193,
    "calibration_slope": 0.5969808623726267,
    "calibration_intercept": -0.06469792949434071
  }
}
```

Plots: `plots/calibration_curves.png`. Detail: `calibration_report.md`.

## 7. Fair market probability methodology

Fair market probability unavailable for this dataset: opposite-side / full-book prices are not present. Raw 1/odds is retained as bookmaker-implied probability only and is NOT treated as margin-free fair probability.

## 8. Calibrated model edge

Primary requested edge is `calibrated_p − fair_market_p`. Because fair market is unavailable, tables use **proxy** `platt_p − raw_implied_p` and label it explicitly as proxy.

| edge_bucket   | edge_definition               |   n |   avg_edge |   win_rate_ex_push |   total_pnl |        roi |   roi_ci_low |   roi_ci_high | clv   |
|:--------------|:------------------------------|----:|-----------:|-------------------:|------------:|-----------:|-------------:|--------------:|:------|
| <0%           | platt_minus_raw_implied_PROXY | 453 | -0.0383817 |           0.587196 |      -31.04 | -0.068521  |    -0.142081 |    0.00576269 |       |
| 0–1%          | platt_minus_raw_implied_PROXY |  50 |  0.0048751 |           0.52     |       -1.98 | -0.0396    |    -0.31501  |    0.21902    |       |
| 1–2%          | platt_minus_raw_implied_PROXY |  32 |  0.013999  |           0.46875  |       -2.96 | -0.0925    |    -0.435406 |    0.257203   |       |
| 2–3%          | platt_minus_raw_implied_PROXY |  36 |  0.023932  |           0.5      |       -2.81 | -0.0780556 |    -0.390833 |    0.217806   |       |
| 3–5%          | platt_minus_raw_implied_PROXY |  37 |  0.0389625 |           0.432432 |       -2.91 | -0.0786486 |    -0.427838 |    0.279223   |       |
| 5–10%         | platt_minus_raw_implied_PROXY |  55 |  0.0731023 |           0.327273 |      -14.8  | -0.269091  |    -0.524395 |    0.0129318  |       |
| 10%+          | platt_minus_raw_implied_PROXY |  17 |  0.129185  |           0.235294 |       -6.55 | -0.385294  |    -0.852941 |    0.185294   |       |

Spearman(proxy edge mid, ROI)=-0.8571428571428573

## 9. CLV analysis

**CLV cannot currently be measured from this dataset.** See `clv_report.md`.

## 10. Market breakdown (OOS, descriptive)

| market           |   n |   win_rate_ex_push |   avg_odds |   total_pnl |        roi |    avg_edge |   avg_platt_prob |   avg_raw_prob | clv   |
|:-----------------|----:|-------------------:|-----------:|------------:|-----------:|------------:|-----------------:|---------------:|:------|
| Over 2.5         | 144 |           0.583333 |    1.6259  |       -8.07 | -0.0560417 | -0.0191203  |         0.604937 |       0.68487  |       |
| BTTS             | 140 |           0.55     |    1.68307 |       -8.8  | -0.0628571 | -0.0203558  |         0.581736 |       0.656925 |       |
| Moneyline        |  99 |           0.424242 |    2.33798 |       -7.35 | -0.0742424 |  0.0166924  |         0.463658 |       0.521494 |       |
| Team Over 1.5    |  69 |           0.449275 |    1.85594 |      -13.62 | -0.197391  |  0.00736683 |         0.559751 |       0.631722 |       |
| Over 1.5         |  64 |           0.71875  |    1.24453 |       -6.67 | -0.104219  | -0.0771422  |         0.729971 |       0.845265 |       |
| Over 3.5         |  52 |           0.442308 |    2.05577 |       -6.52 | -0.125385  |  0.0176739  |         0.514943 |       0.580209 |       |
| Double Chance 1X |  51 |           0.568627 |    1.60333 |       -8.08 | -0.158431  | -0.0192761  |         0.629079 |       0.714972 |       |
| Double Chance X2 |  40 |           0.6      |    1.6915  |        0.87 |  0.02175   | -0.00887787 |         0.590164 |       0.666972 |       |
| Under 2.5        |  17 |           0.352941 |    1.90353 |       -5.14 | -0.302353  |  0.025913   |         0.557004 |       0.627566 |       |
| Draw             |   4 |           0.25     |    4.445   |        0.33 |  0.0825    |  0.0456939  |         0.275076 |       0.289029 |       |

## 11. Odds breakdown (OOS, fixed bands)

| odds_band   |   n |        roi |   avg_edge |   calibration_error_platt |   avg_odds |   total_pnl | clv   |
|:------------|----:|-----------:|-----------:|--------------------------:|-----------:|------------:|:------|
| 1.00–1.30   |  59 | -0.118305  | -0.08338   |                -0.0159236 |    1.20983 |       -6.98 |       |
| 1.30–1.50   |  97 | -0.11134   | -0.045191  |                -0.0341703 |    1.39361 |      -10.8  |       |
| 1.50–1.70   | 169 | -0.141302  | -0.0248182 |                -0.0667627 |    1.58976 |      -23.88 |       |
| 1.70–1.90   | 134 | -0.038806  | -0.0100282 |                -0.0111321 |    1.76851 |       -5.2  |       |
| 1.90–2.10   |  93 | -0.0966667 |  0.0158785 |                -0.0642901 |    1.95892 |       -8.99 |       |
| 2.10–2.50   |  78 |  0.114103  |  0.0220638 |                 0.0282003 |    2.22846 |        8.9  |       |
| 2.50–3.00   |  35 | -0.332286  |  0.0546725 |                -0.180445  |    2.616   |      -11.63 |       |
| 3.00+       |  15 | -0.298     |  0.103636  |                -0.180633  |    3.70867 |       -4.47 |       |

## 12. League breakdown (OOS)

| league                |   n |   win_rate_ex_push |         roi |   total_pnl |   avg_odds |     avg_edge | sample_flag    | clv   |
|:----------------------|----:|-------------------:|------------:|------------:|-----------:|-------------:|:---------------|:------|
| Major League Soccer   |  87 |           0.436782 | -0.284023   |      -24.71 |    1.76034 | -0.00820248  | sufficient     |       |
| Serie A               |  52 |           0.692308 |  0.204615   |       10.64 |    1.77635 | -0.0101473   | sufficient     |       |
| Eerste Divisie        |  46 |           0.521739 | -0.135      |       -6.21 |    1.76174 | -0.0108779   | sufficient     |       |
| Super League          |  45 |           0.666667 |  0.127333   |        5.73 |    1.77444 | -0.00964602  | sufficient     |       |
| Eredivisie            |  43 |           0.697674 |  0.145349   |        6.25 |    1.66953 | -0.02215     | sufficient     |       |
| Championship          |  41 |           0.536585 | -0.0395122  |       -1.62 |    1.94537 | -0.00256471  | sufficient     |       |
| Allsvenskan           |  41 |           0.365854 | -0.402927   |      -16.52 |    1.77146 | -0.00957906  | sufficient     |       |
| Jupiler Pro League    |  30 |           0.566667 |  0.00366667 |        0.11 |    1.96167 | -0.0107301   | sufficient     |       |
| 2. Bundesliga         |  28 |           0.357143 | -0.356429   |       -9.98 |    1.84036 | -0.0131876   | insufficient_n |       |
| Pro League            |  26 |           0.384615 | -0.405      |      -10.53 |    1.59769 | -0.0192772   | insufficient_n |       |
| Superliga             |  23 |           0.478261 | -0.183478   |       -4.22 |    1.74696 | -0.0112422   | insufficient_n |       |
| Süper Lig             |  22 |           0.318182 | -0.504545   |      -11.1  |    1.81318 | -0.00548053  | insufficient_n |       |
| Bundesliga            |  21 |           0.428571 | -0.308095   |       -6.47 |    1.75476 | -0.0205825   | insufficient_n |       |
| Primeira Liga         |  21 |           0.52381  |  0.00047619 |        0.01 |    1.96524 | -0.00211561  | insufficient_n |       |
| Liga MX               |  21 |           0.666667 |  0.200476   |        4.21 |    1.91238 |  0.00103907  | insufficient_n |       |
| Premiership           |  17 |           0.470588 | -0.21       |       -3.57 |    1.71294 | -0.0193907   | insufficient_n |       |
| Eliteserien           |  16 |           0.625    |  0.05375    |        0.86 |    1.67125 | -0.023528    | insufficient_n |       |
| Ligue 1               |  14 |           0.714286 |  0.202857   |        2.84 |    1.72571 | -0.0357781   | insufficient_n |       |
| UEFA Europa League    |  13 |           0.384615 | -0.413077   |       -5.37 |    1.69308 | -0.0287747   | insufficient_n |       |
| La Liga               |  12 |           0.666667 |  0.230833   |        2.77 |    1.84667 | -0.0156121   | insufficient_n |       |
| League Cup            |  12 |           0.666667 |  0.145833   |        1.75 |    1.81333 | -0.00687727  | insufficient_n |       |
| UEFA Champions League |  12 |           0.75     |  0.1975     |        2.37 |    1.63167 | -0.0263889   | insufficient_n |       |
| Premier League        |  10 |           0.6      |  0.014      |        0.14 |    2.011   | -0.00477084  | insufficient_n |       |
| Leagues Cup           |   9 |           0.444444 | -0.263333   |       -2.37 |    1.74    | -0.0196733   | insufficient_n |       |
| Copa Do Brasil        |   6 |           0.666667 |  0.326667   |        1.96 |    1.92333 |  0.000675423 | insufficient_n |       |
| CONMEBOL Sudamericana |   4 |           1        |  0.8        |        3.2  |    1.8     | -0.0169224   | insufficient_n |       |
| US Open Cup           |   4 |           0.5      | -0.1375     |       -0.55 |    1.9875  |  0.0132777   | insufficient_n |       |
| Coppa Italia          |   3 |           0        | -1          |       -3    |    1.74    | -0.0220969   | insufficient_n |       |
| DFB Pokal             |   1 |           1        |  0.33       |        0.33 |    1.33    | -0.053647    | insufficient_n |       |

## 13. Temporal stability (OOS months)

| month   |   n |        roi |   win_rate_ex_push |   avg_edge |   total_pnl | clv   |
|:--------|----:|-----------:|-------------------:|-----------:|------------:|:------|
| 2026-09 | 680 | -0.0927206 |           0.533824 | -0.0120224 |      -63.05 |       |

## 14. Statistical uncertainty

```json
{
  "oos_roi_bootstrap": {
    "mean": -0.09351629411764704,
    "ci_low": -0.15739779411764707,
    "ci_high": -0.027552941176470613
  },
  "oos_baseline": {
    "bets": 680,
    "wins": 363,
    "losses": 317,
    "pushes": 0,
    "win_rate_ex_push": 0.5338235294117647,
    "average_odds": 1.7873529411764708,
    "total_pnl": -63.05,
    "roi": -0.09272058823529411,
    "max_drawdown": -66.01000000000002,
    "profit_factor": 0.8011041009463722,
    "pnl_std": 0.8916109321682585,
    "sharpe_like": -2.7117849726914907
  }
}
```

## 15. Season 3 / future validation

```json
{
  "status": "unavailable",
  "message": "No --future CSV provided or file missing. True future-season validation not run."
}
```

Protocol: `future_validation_protocol.md`.

## 16. What survived out-of-sample

- Probability calibration improvement (Platt/isotonic vs raw) on walk-forward folds.

## 17. What failed

- Aggregate OOS betting profitability at flat 1u (ROI CI below zero).
- Measurement of fair-market edge and CLV (data missing).

## 18. What remains inconclusive

- Whether calibrated probabilities beat **true** fair market prices.
- League/market/odds descriptive slices without future-season confirmation.
- Predefined edge-threshold sensitivity results (see table; not optimized).

| rule                                 |   threshold |   n |        roi |   total_pnl |   win_rate_ex_push |   avg_odds |   max_drawdown |   roi_ci_low |   roi_ci_high |
|:-------------------------------------|------------:|----:|-----------:|------------:|-------------------:|-----------:|---------------:|-------------:|--------------:|
| all OOS bets (no edge filter)        |      nan    | 680 | -0.0927206 |      -63.05 |           0.533824 |    1.78735 |         -66.01 |    -0.157157 |  -0.0273199   |
| model_edge_vs_raw_implied_platt > 1% |        0.01 | 177 | -0.169661  |      -30.03 |           0.40113  |    2.21859 |         -30.21 |    -0.319777 |  -0.0171596   |
| model_edge_vs_raw_implied_platt > 2% |        0.02 | 145 | -0.18669   |      -27.07 |           0.386207 |    2.25759 |         -27.72 |    -0.373869 |  -0.000344828 |
| model_edge_vs_raw_implied_platt > 3% |        0.03 | 109 | -0.222569  |      -24.26 |           0.348624 |    2.35505 |         -24.91 |    -0.43233  |  -0.00722936  |
| model_edge_vs_raw_implied_platt > 5% |        0.05 |  72 | -0.296528  |      -21.35 |           0.305556 |    2.50333 |         -21.73 |    -0.531538 |  -0.0395799   |

## 19. Recommended next research step

Instrument odds capture: opposite-side books + closing lines. Re-run frozen v2 on Season 3 once available.

## Final questions

### 1. Are the model probabilities calibrated after walk-forward Platt/isotonic calibration?

Improved but not perfect. OOS ECE raw=0.122, Platt=0.044, isotonic=0.043. Platt slope=0.837 (1.0 = ideal).

### 2. Does calibrated probability predict outcomes better than the raw model?

Yes on proper scoring rules OOS: Brier raw=0.2572 vs Platt=0.2440, isotonic=0.2442.

### 3. Does calibrated probability beat fair market probability?

Fair market probability unavailable for this dataset: opposite-side / full-book prices are not present. Raw 1/odds is retained as bookmaker-implied probability only and is NOT treated as margin-free fair probability. Therefore this question cannot be answered with margin-free fair prices on Season 2. Proxy edge vs raw implied is reported separately and must not be equated with beating the fair market.

### 4. Does positive calibrated edge correspond to positive realized ROI?

Using proxy edge vs raw implied: inspect edge-bucket table. No robust positive mapping established.

### 5. Does increasing calibrated edge correspond to increasing realized ROI?

Spearman(proxy edge bucket mid vs ROI)=-0.8571428571428573. No — higher proxy edge buckets had worse OOS ROI (inverted).

### 6. Is there positive CLV?

CLV cannot currently be measured from this dataset.

### 7. Does positive CLV correspond to future profitability?

Not applicable — CLV unavailable.

### 8. Which markets show persistent evidence of model-vs-market disagreement?

See OOS market table (descriptive). Do not treat top ROI markets as selected strategies. Without fair prices, 'disagreement with market' is not rigorously measurable.

### 9. Which odds ranges show persistent evidence?

See OOS odds table (descriptive, fixed bands). Prior 2.10–2.50 result is hypothesis only — not optimized here.

### 10. Are league effects robust or merely historical variance?

OOS league ROIs with N≥30 are hypotheses only; without Season 3 confirmation treat as historical variance.

### 11. Does any fixed edge threshold show positive OOS performance?

Predefined proxy-edge thresholds 1%/2%/3%/5% were all negative OOS (no positive threshold). Not a deployable rule set.

### 12. Does a completely untouched future season confirm the edge?

No — Season 3/future season dataset unavailable. See future_validation_protocol.md.

### 13. What is the strongest evidence FOR a genuine betting edge?

Walk-forward calibration improves probability scores (lower Brier/ECE). That supports better uncertainty estimates, not a betting edge.

### 14. What is the strongest evidence AGAINST a genuine betting edge?

OOS flat-1u ROI=-0.0927 with bootstrap 95% CI [-0.1574, -0.0276]; proxy edge→ROI Spearman negative; fair-market edge & CLV unmeasurable.

### 15. What must happen before we should consider changing production?

1) Collect opposite-side/closing odds for fair market + CLV. 2) Run frozen methodology on untouched Season 3 once. 3) Require non-inverted edge→ROI and preferably positive CLV with adequate N. 4) Do not change production filters based on Season 2 mining.

## Bottom line

**No deployable edge established yet.**