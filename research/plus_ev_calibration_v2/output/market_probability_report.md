# Market probability / fair market report

Fair market probability unavailable for this dataset: opposite-side / full-book prices are not present. Raw 1/odds is retained as bookmaker-implied probability only and is NOT treated as margin-free fair probability.

```json
{
  "rows": 1900,
  "fair_market_available_n": 0,
  "fair_market_available_pct": 0.0,
  "statement": "Fair market probability unavailable for this dataset: opposite-side / full-book prices are not present. Raw 1/odds is retained as bookmaker-implied probability only and is NOT treated as margin-free fair probability."
}
```

## OOS markets (descriptive)
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

## OOS odds bands (fixed, descriptive)
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

## Proxy edge buckets (Platt − raw implied; NOT fair-market edge)
| edge_bucket   | edge_definition               |   n |   avg_edge |   win_rate_ex_push |   total_pnl |        roi |   roi_ci_low |   roi_ci_high | clv   |
|:--------------|:------------------------------|----:|-----------:|-------------------:|------------:|-----------:|-------------:|--------------:|:------|
| <0%           | platt_minus_raw_implied_PROXY | 453 | -0.0383817 |           0.587196 |      -31.04 | -0.068521  |    -0.142081 |    0.00576269 |       |
| 0–1%          | platt_minus_raw_implied_PROXY |  50 |  0.0048751 |           0.52     |       -1.98 | -0.0396    |    -0.31501  |    0.21902    |       |
| 1–2%          | platt_minus_raw_implied_PROXY |  32 |  0.013999  |           0.46875  |       -2.96 | -0.0925    |    -0.435406 |    0.257203   |       |
| 2–3%          | platt_minus_raw_implied_PROXY |  36 |  0.023932  |           0.5      |       -2.81 | -0.0780556 |    -0.390833 |    0.217806   |       |
| 3–5%          | platt_minus_raw_implied_PROXY |  37 |  0.0389625 |           0.432432 |       -2.91 | -0.0786486 |    -0.427838 |    0.279223   |       |
| 5–10%         | platt_minus_raw_implied_PROXY |  55 |  0.0731023 |           0.327273 |      -14.8  | -0.269091  |    -0.524395 |    0.0129318  |       |
| 10%+          | platt_minus_raw_implied_PROXY |  17 |  0.129185  |           0.235294 |       -6.55 | -0.385294  |    -0.852941 |    0.185294   |       |

## Predefined edge-threshold sensitivity (report all)
| rule                                 |   threshold |   n |        roi |   total_pnl |   win_rate_ex_push |   avg_odds |   max_drawdown |   roi_ci_low |   roi_ci_high |
|:-------------------------------------|------------:|----:|-----------:|------------:|-------------------:|-----------:|---------------:|-------------:|--------------:|
| all OOS bets (no edge filter)        |      nan    | 680 | -0.0927206 |      -63.05 |           0.533824 |    1.78735 |         -66.01 |    -0.157157 |  -0.0273199   |
| model_edge_vs_raw_implied_platt > 1% |        0.01 | 177 | -0.169661  |      -30.03 |           0.40113  |    2.21859 |         -30.21 |    -0.319777 |  -0.0171596   |
| model_edge_vs_raw_implied_platt > 2% |        0.02 | 145 | -0.18669   |      -27.07 |           0.386207 |    2.25759 |         -27.72 |    -0.373869 |  -0.000344828 |
| model_edge_vs_raw_implied_platt > 3% |        0.03 | 109 | -0.222569  |      -24.26 |           0.348624 |    2.35505 |         -24.91 |    -0.43233  |  -0.00722936  |
| model_edge_vs_raw_implied_platt > 5% |        0.05 |  72 | -0.296528  |      -21.35 |           0.305556 |    2.50333 |         -21.73 |    -0.531538 |  -0.0395799   |