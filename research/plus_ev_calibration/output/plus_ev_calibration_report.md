# Plus EV Calibration Research Report (Season 2)

_Generated: 2026-09-19T04:32:49.367262Z_

## 1. Executive summary

Season 2 log: 1900 rows, 1755 settled. Baseline settled ROI=-0.0520 (-91.25u). OOS 50/50 ROI=-0.0607 (95% CI -0.1204–-0.0012). Raw probabilities are miscalibrated (ECE=0.096). Candidate strategy OOS ROI=-0.0333 on 18 bets.

## 2. Data-quality report

```json
{
  "columns_detected": [
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
    "resolved_at",
    "status_norm",
    "ev_decimal",
    "market_implied_probability",
    "raw_model_probability",
    "raw_ev_reconstructed",
    "break_even_probability",
    "market_group",
    "is_settled",
    "outcome_win",
    "pnl_calc"
  ],
  "column_dtypes": {
    "id": "str",
    "created_at": "str",
    "fixture_date": "str",
    "fixture": "str",
    "league_name": "str",
    "bet_type": "str",
    "category": "str",
    "market": "str",
    "team_name": "str",
    "qualifier_pct": "float64",
    "odds": "float64",
    "units": "float64",
    "status": "str",
    "pnl_units": "float64",
    "resolved_at": "str"
  },
  "ev_source_column": "qualifier_pct",
  "total_rows": 1900,
  "settled_rows": 1755,
  "wins": 980,
  "losses": 766,
  "pushes": 9,
  "open_unsettled": 145,
  "duplicate_id_groups": 0,
  "chronological_sort": [
    "fixture_date",
    "created_at"
  ],
  "date_range_fixture": [
    "2026-07-03 17:00:00+00:00",
    "2026-09-20 03:15:00+00:00"
  ],
  "pnl_units_vs_calc_max_abs_diff_settled": 2.220446049250313e-16,
  "ev_formula_validation_samples": [
    {
      "market": "Over 2.5",
      "qualifier_pct": 10.2,
      "odds": 1.67,
      "ev_decimal": 0.102,
      "raw_model_probability": 0.6598802395209582,
      "raw_ev_reconstructed": 0.10200000000000009
    },
    {
      "market": "Sirius O1.5",
      "qualifier_pct": 9.2,
      "odds": 1.62,
      "ev_decimal": 0.092,
      "raw_model_probability": 0.674074074074074,
      "raw_ev_reconstructed": 0.09200000000000008
    },
    {
      "market": "Sirius Win",
      "qualifier_pct": 7.5,
      "odds": 1.67,
      "ev_decimal": 0.075,
      "raw_model_probability": 0.6437125748502994,
      "raw_ev_reconstructed": 0.07499999999999996
    },
    {
      "market": "Over 1.5",
      "qualifier_pct": 2.5,
      "odds": 1.2,
      "ev_decimal": 0.025,
      "raw_model_probability": 0.8541666666666666,
      "raw_ev_reconstructed": 0.02499999999999991
    },
    {
      "market": "Elfsborg Win",
      "qualifier_pct": 68.5,
      "odds": 3.9,
      "ev_decimal": 0.685,
      "raw_model_probability": 0.43205128205128207,
      "raw_ev_reconstructed": 0.685
    }
  ]
}
```

## 3. Baseline performance (all settled bets, flat 1u)

```json
{
  "bets": 1755,
  "wins": 980,
  "losses": 766,
  "pushes": 9,
  "win_rate_ex_push": 0.561282932416953,
  "average_odds": 1.7818347578347578,
  "total_stake_units": 1755.0,
  "total_pnl": -91.24999999999997,
  "roi": -0.05199430199430198,
  "avg_profit_per_bet": -0.05199430199430198,
  "max_drawdown": -95.83000000000025,
  "profit_factor": 0.8808746736292428,
  "pnl_std": 0.8840082538630275,
  "sharpe_like": -2.4639846204506584
}
```

## 4. Calibration curve results

- Brier (raw prob, settled): **0.2431**
- Log loss (raw): **0.6806**
- ECE (raw, 10 bins): **0.0960**

### Probability bins (raw model probability)

| bin       |   bets |   mean_predicted_prob |   actual_win_rate |   calibration_error |   avg_odds |   total_pnl |          roi |
|:----------|-------:|----------------------:|------------------:|--------------------:|-----------:|------------:|-------------:|
| 0.50–0.55 |    148 |              0.527574 |          0.425676 |          -0.101898  |    2.21385 |      -10.36 | -0.07        |
| 0.55–0.60 |    264 |              0.577739 |          0.518939 |          -0.0587991 |    1.97606 |        6.21 |  0.0235227   |
| 0.60–0.65 |    341 |              0.624529 |          0.548387 |          -0.076142  |    1.79686 |       -7.27 | -0.0213196   |
| 0.65–0.70 |    305 |              0.674914 |          0.52459  |          -0.150324  |    1.65652 |      -43.57 | -0.142852    |
| 0.70–0.75 |    211 |              0.723107 |          0.597156 |          -0.125951  |    1.52469 |      -19.79 | -0.0937915   |
| 0.75–0.80 |    133 |              0.773233 |          0.744361 |          -0.028872  |    1.40707 |        6.11 |  0.0459398   |
| 0.80–0.85 |     93 |              0.822768 |          0.774194 |          -0.0485744 |    1.31645 |        1.64 |  0.0176344   |
| 0.85–0.90 |     80 |              0.874117 |          0.7      |          -0.174117  |    1.204   |      -12.65 | -0.158125    |
| 0.90–0.95 |     34 |              0.921813 |          0.882353 |          -0.03946   |    1.13471 |       -0.01 | -0.000294118 |
| 0.95–1.01 |      3 |              0.964263 |          1        |           0.0357373 |    1.07    |        0.21 |  0.07        |

### Calibration curve sample points (predicted vs observed)

|   mean_predicted |   fraction_positive |
|-----------------:|--------------------:|
|         0.45622  |            0.377143 |
|         0.544209 |            0.462857 |
|         0.582689 |            0.534483 |
|         0.609212 |            0.542857 |
|         0.634625 |            0.528736 |
|         0.662427 |            0.528409 |
|         0.690242 |            0.526012 |
|         0.725836 |            0.594286 |
|         0.779234 |            0.741379 |
|         0.871031 |            0.777143 |

_Perfect calibration lies on the diagonal (predicted = observed)._

## 5. Raw vs calibrated probabilities

Walk-forward expanding window (isotonic) used for out-of-sample calibrated probabilities.

## 6. Walk-forward methodology

- Sort bets by `fixture_date`, then `created_at`.
- **Primary OOS:** first 50% train → calibrate on train settled → evaluate test 50%.
- **Robustness:** 70% train / 30% test split with same protocol.
- **Strict walk-forward:** expanding-window refit before each test row (min 200 prior settled bets).
- No future outcomes used when calibrating a given prediction.

## 7. Strategy comparison (out-of-sample, 50/50 split)

|                           |   bets |   wins |   losses |   pushes |   win_rate_ex_push |   average_odds |   total_stake_units |   total_pnl |        roi |   avg_profit_per_bet |   max_drawdown |   profit_factor |   pnl_std |   sharpe_like | strategy   |
|:--------------------------|-------:|-------:|---------:|---------:|-------------------:|---------------:|--------------------:|------------:|-----------:|---------------------:|---------------:|----------------:|----------:|--------------:|:-----------|
| A_reported_ev_all_bets    |    878 |    480 |      389 |        9 |           0.552359 |        1.78658 |                 878 |      -53.28 | -0.0606834 |           -0.0606834 |         -79.21 |        0.863033 |  0.885592 |      -2.03041 | A          |
| B_raw_prob_ev_all_bets    |    878 |    480 |      389 |        9 |           0.552359 |        1.78658 |                 878 |      -53.28 | -0.0606834 |           -0.0606834 |         -79.21 |        0.863033 |  0.885592 |      -2.03041 | B          |
| C_calibrated_ev_all_bets  |    878 |    480 |      389 |        9 |           0.552359 |        1.78658 |                 878 |      -53.28 | -0.0606834 |           -0.0606834 |         -79.21 |        0.863033 |  0.885592 |      -2.03041 | C          |
| walkforward_expanding_all |   1546 |    886 |      660 |        0 |           0.573092 |        1.78208 |                1546 |      -47.31 | -0.0306016 |           -0.0306016 |         -79.21 |        0.928318 |  0.886024 |      -1.35801 | WF         |

### 70/30 split (robustness)

|                          |   bets |   wins |   losses |   pushes |   win_rate_ex_push |   average_odds |   total_stake_units |   total_pnl |        roi |   avg_profit_per_bet |   max_drawdown |   profit_factor |   pnl_std |   sharpe_like | strategy   |
|:-------------------------|-------:|-------:|---------:|---------:|-------------------:|---------------:|--------------------:|------------:|-----------:|---------------------:|---------------:|----------------:|----------:|--------------:|:-----------|
| A_reported_ev_all_bets   |    527 |    277 |      241 |        9 |           0.534749 |          1.773 |                 527 |      -42.53 | -0.0807021 |           -0.0807021 |         -49.09 |        0.823527 |  0.895615 |      -2.06856 | A          |
| B_raw_prob_ev_all_bets   |    527 |    277 |      241 |        9 |           0.534749 |          1.773 |                 527 |      -42.53 | -0.0807021 |           -0.0807021 |         -49.09 |        0.823527 |  0.895615 |      -2.06856 | B          |
| C_calibrated_ev_all_bets |    527 |    277 |      241 |        9 |           0.534749 |          1.773 |                 527 |      -42.53 | -0.0807021 |           -0.0807021 |         -49.09 |        0.823527 |  0.895615 |      -2.06856 | C          |

## 8. EV bucket analysis (OOS test half, 50/50)

### Reported / raw EV buckets

| ev_bucket   | ev_type      |   bets |   win_rate_ex_push |   avg_odds |   total_pnl |        roi |
|:------------|:-------------|-------:|-------------------:|-----------:|------------:|-----------:|
| 0–3%        | raw_reported |     23 |           0.826087 |    1.23957 |        0.63 |  0.0273913 |
| 3–5%        | raw_reported |    170 |           0.619048 |    1.53047 |      -12.37 | -0.0727647 |
| 5–10%       | raw_reported |    278 |           0.59854  |    1.64007 |       -8.39 | -0.0301799 |
| 10–15%      | raw_reported |    183 |           0.519337 |    1.79514 |      -11.69 | -0.0638798 |
| 15–20%      | raw_reported |     99 |           0.55102  |    1.96879 |        5.23 |  0.0528283 |
| 20–30%      | raw_reported |     71 |           0.422535 |    2.21211 |       -8.38 | -0.118028  |
| 30%+        | raw_reported |     54 |           0.277778 |    2.65759 |      -18.31 | -0.339074  |

### Calibrated EV buckets

| ev_bucket   | ev_type    |   bets |   win_rate_ex_push |   avg_odds |   total_pnl |        roi |
|:------------|:-----------|-------:|-------------------:|-----------:|------------:|-----------:|
| 0–3%        | calibrated |    108 |           0.592593 |    1.65815 |       -5.62 | -0.052037  |
| 3–5%        | calibrated |     47 |           0.446809 |    1.62723 |      -14.57 | -0.31      |
| 5–10%       | calibrated |     78 |           0.525641 |    1.84667 |       -9.71 | -0.124487  |
| 10–15%      | calibrated |     28 |           0.607143 |    1.8525  |        1.02 |  0.0364286 |
| 15–20%      | calibrated |     16 |           0.5      |    2.43875 |        2.29 |  0.143125  |
| 20–30%      | calibrated |      8 |           0.375    |    2.34    |       -1.55 | -0.19375   |
| 30%+        | calibrated |      9 |           0.222222 |    3.25778 |       -4.4  | -0.488889  |

Spearman (EV mid vs ROI), raw EV buckets: **-0.536**
Spearman (EV mid vs ROI), calibrated EV buckets: **-0.250**

## 9. Market analysis

### In-sample (all settled)

| market           | sample    |   bets |   win_rate_ex_push |   avg_odds |   total_pnl |         roi |   avg_raw_ev |   avg_calibrated_ev |
|:-----------------|:----------|-------:|-------------------:|-----------:|------------:|------------:|-------------:|--------------------:|
| Over 2.5         | in_sample |    367 |           0.621253 |    1.63706 |        2.23 |  0.00607629 |    0.101747  |                 nan |
| BTTS             | in_sample |    347 |           0.585014 |    1.68432 |       -6.8  | -0.0195965  |    0.0930692 |                 nan |
| Moneyline        | in_sample |    257 |           0.424125 |    2.27875 |      -27.12 | -0.105525   |    0.183591  |                 nan |
| Team Over 1.5    | in_sample |    189 |           0.481481 |    1.81677 |      -29.72 | -0.157249   |    0.147063  |                 nan |
| Over 1.5         | in_sample |    173 |           0.768786 |    1.23324 |       -9.47 | -0.0547399  |    0.0467283 |                 nan |
| Double Chance 1X | in_sample |    147 |           0.571429 |    1.57837 |      -20    | -0.136054   |    0.112388  |                 nan |
| Over 3.5         | in_sample |    133 |           0.518797 |    2.07744 |        7.39 |  0.0555639  |    0.178782  |                 nan |
| Double Chance X2 | in_sample |     65 |           0.523077 |    1.69985 |       -6.83 | -0.105077   |    0.121585  |                 nan |
| Under 2.5        | in_sample |     50 |           0.46     |    1.8732  |       -6.39 | -0.1278     |    0.17002   |                 nan |
| Draw             | in_sample |     18 |           0.333333 |    4.01611 |        5.46 |  0.303333   |    0.185611  |                 nan |

### Out-of-sample (50/50 test)

| market           | sample    |   bets |   win_rate_ex_push |   avg_odds |   total_pnl |         roi |   avg_raw_ev |   avg_calibrated_ev |
|:-----------------|:----------|-------:|-------------------:|-----------:|------------:|------------:|-------------:|--------------------:|
| Over 2.5         | oos_50_50 |    188 |           0.602151 |    1.63324 |       -3.49 | -0.0185638  |    0.100745  |          -0.0299323 |
| BTTS             | oos_50_50 |    181 |           0.569832 |    1.68105 |       -6.79 | -0.0375138  |    0.092105  |          -0.0573109 |
| Moneyline        | oos_50_50 |    126 |           0.452381 |    2.29889 |       -4.66 | -0.0369841  |    0.181294  |          -0.081032  |
| Team Over 1.5    | oos_50_50 |     93 |           0.434783 |    1.84333 |      -21.88 | -0.235269   |    0.155634  |          -0.0125209 |
| Over 1.5         | oos_50_50 |     83 |           0.740741 |    1.24024 |       -6.63 | -0.0798795  |    0.0475783 |          -0.0104277 |
| Over 3.5         | oos_50_50 |     69 |           0.507246 |    2.04855 |        0.32 |  0.00463768 |    0.171797  |          -0.049842  |
| Double Chance 1X | oos_50_50 |     62 |           0.583333 |    1.60806 |       -7.75 | -0.125      |    0.117677  |          -0.0101457 |
| Double Chance X2 | oos_50_50 |     47 |           0.638298 |    1.69723 |        4.31 |  0.0917021  |    0.124787  |          -0.0148727 |
| Under 2.5        | oos_50_50 |     22 |           0.318182 |    1.89955 |       -7.84 | -0.356364   |    0.186818  |           0.0189262 |
| Draw             | oos_50_50 |      7 |           0.285714 |    4.38    |        1.13 |  0.161429   |    0.261286  |           0.095     |

## 10. Odds analysis

### In-sample

|   bets |   wins |   losses |   pushes |   win_rate_ex_push |   average_odds |   total_stake_units |   total_pnl |         roi |   avg_profit_per_bet |   max_drawdown |   profit_factor |   pnl_std |   sharpe_like | odds_band   | sample    |
|-------:|-------:|---------:|---------:|-------------------:|---------------:|--------------------:|------------:|------------:|---------------------:|---------------:|----------------:|----------:|--------------:|:------------|:----------|
|    160 |    126 |       34 |        0 |           0.7875   |        1.19925 |                 160 |       -9.09 | -0.0568125  |          -0.0568125  |         -10.33 |        0.732647 |  0.494094 |     -1.45444  | 1.00–1.30   | in_sample |
|    236 |    168 |       68 |        0 |           0.711864 |        1.39581 |                 236 |       -1.94 | -0.00822034 |          -0.00822034 |         -12.36 |        0.971471 |  0.633697 |     -0.19928  | 1.30–1.50   | in_sample |
|    451 |    255 |      196 |        0 |           0.56541  |        1.59064 |                 451 |      -46.1  | -0.102217   |          -0.102217   |         -54.21 |        0.764796 |  0.789455 |     -2.7497   | 1.50–1.70   | in_sample |
|    339 |    180 |      159 |        0 |           0.530973 |        1.77324 |                 339 |      -20.61 | -0.0607965  |          -0.0607965  |         -29.5  |        0.870377 |  0.884802 |     -1.26512  | 1.70–1.90   | in_sample |
|    239 |    125 |      114 |        0 |           0.523013 |        1.95799 |                 239 |        5.63 |  0.0235565  |           0.0235565  |         -12.49 |        1.04939  |  0.980194 |      0.371533 | 1.90–2.10   | in_sample |
|    209 |     96 |      113 |        0 |           0.45933  |        2.22469 |                 209 |        4.78 |  0.0228708  |           0.0228708  |         -23.27 |        1.0423   |  1.11488  |      0.29657  | 2.10–2.50   | in_sample |
|     68 |     20 |       48 |        0 |           0.294118 |        2.62676 |                  68 |      -15.78 | -0.232059   |          -0.232059   |         -24.51 |        0.67125  |  1.20006  |     -1.59459  | 2.50–3.00   | in_sample |
|     44 |     10 |       34 |        0 |           0.227273 |        3.66    |                  44 |       -8.14 | -0.185      |          -0.185      |         -10.67 |        0.760588 |  1.53708  |     -0.798367 | 3.00+       | in_sample |

### Out-of-sample

|   bets |   wins |   losses |   pushes |   win_rate_ex_push |   average_odds |   total_stake_units |   total_pnl |        roi |   avg_profit_per_bet |   max_drawdown |   profit_factor |   pnl_std |   sharpe_like | odds_band   | sample    |
|-------:|-------:|---------:|---------:|-------------------:|---------------:|--------------------:|------------:|-----------:|---------------------:|---------------:|----------------:|----------:|--------------:|:------------|:----------|
|     74 |     54 |       18 |        2 |           0.75     |        1.20324 |                  74 |       -7.13 | -0.0963514 |           -0.0963514 |          -9.62 |        0.603889 |  0.519511 |     -1.59543  | 1.00–1.30   | oos_50_50 |
|    125 |     87 |       38 |        0 |           0.696    |        1.39296 |                 125 |       -4.07 | -0.03256   |           -0.03256   |         -12.36 |        0.892895 |  0.643325 |     -0.56586  | 1.30–1.50   | oos_50_50 |
|    218 |    117 |       99 |        2 |           0.541667 |        1.59005 |                 218 |      -29.52 | -0.135413  |           -0.135413  |         -34.22 |        0.701818 |  0.793825 |     -2.51862  | 1.50–1.70   | oos_50_50 |
|    179 |     93 |       81 |        5 |           0.534483 |        1.7719  |                 179 |       -9.55 | -0.053352  |           -0.053352  |         -20.67 |        0.882099 |  0.872916 |     -0.817719 | 1.70–1.90   | oos_50_50 |
|    122 |     63 |       59 |        0 |           0.516393 |        1.96    |                 122 |        1.22 |  0.01      |            0.01      |         -11.75 |        1.02068  |  0.982063 |      0.112471 | 1.90–2.10   | oos_50_50 |
|    101 |     52 |       49 |        0 |           0.514851 |        2.22604 |                 101 |       14.45 |  0.143069  |            0.143069  |          -7.06 |        1.2949   |  1.11838  |      1.28564  | 2.10–2.50   | oos_50_50 |
|     40 |     10 |       30 |        0 |           0.25     |        2.6275  |                  40 |      -14.01 | -0.35025   |           -0.35025   |         -16.63 |        0.533    |  1.14135  |     -1.94084  | 2.50–3.00   | oos_50_50 |
|     19 |      4 |       15 |        0 |           0.210526 |        3.82158 |                  19 |       -4.67 | -0.245789  |           -0.245789  |         -10    |        0.688667 |  1.52025  |     -0.704732 | 3.00+       | oos_50_50 |

## 11. League analysis

| league                        |   bets |   win_rate_ex_push |   total_pnl |         roi |   avg_odds |   avg_raw_ev | sample_flag    |
|:------------------------------|-------:|-------------------:|------------:|------------:|-----------:|-------------:|:---------------|
| Major League Soccer           |    272 |           0.514706 |      -35.54 | -0.130662   |    1.77699 |    0.139853  | sufficient     |
| Allsvenskan                   |    143 |           0.440559 |      -44.2  | -0.309091   |    1.79077 |    0.145503  | sufficient     |
| Serie A                       |    143 |           0.615385 |       16.69 |  0.116713   |    1.86091 |    0.122776  | sufficient     |
| Super League                  |     94 |           0.638298 |        4.32 |  0.0459574  |    1.72649 |    0.117319  | sufficient     |
| Leagues Cup                   |     92 |           0.576087 |       -4.54 | -0.0493478  |    1.7     |    0.116989  | sufficient     |
| Eerste Divisie                |     91 |           0.659341 |        7.81 |  0.0858242  |    1.7489  |    0.114242  | sufficient     |
| Eliteserien                   |     88 |           0.590909 |       -5.14 | -0.0584091  |    1.71523 |    0.122318  | sufficient     |
| Superliga                     |     83 |           0.554217 |       -5.79 | -0.069759   |    1.76036 |    0.123048  | sufficient     |
| Eredivisie                    |     77 |           0.675325 |        6.51 |  0.0845455  |    1.66104 |    0.0972597 | sufficient     |
| 2. Bundesliga                 |     63 |           0.47619  |       -8.87 | -0.140794   |    1.80254 |    0.107492  | sufficient     |
| Liga MX                       |     60 |           0.583333 |        5.13 |  0.0855     |    2.0155  |    0.157767  | sufficient     |
| Pro League                    |     54 |           0.481481 |      -11.53 | -0.213519   |    1.63481 |    0.109148  | sufficient     |
| Bundesliga                    |     51 |           0.647059 |        2    |  0.0392157  |    1.7051  |    0.0970784 | sufficient     |
| Championship                  |     48 |           0.5      |       -5.26 | -0.109583   |    1.925   |    0.134458  | sufficient     |
| UEFA Champions League         |     40 |           0.65     |        2.03 |  0.05075    |    1.673   |    0.121425  | sufficient     |
| Jupiler Pro League            |     40 |           0.6      |        2.15 |  0.05375    |    1.92175 |    0.1276    | sufficient     |
| Süper Lig                     |     39 |           0.461538 |       -8.76 | -0.224615   |    1.81077 |    0.116538  | sufficient     |
| Premiership                   |     39 |           0.538462 |       -3.44 | -0.0882051  |    1.72744 |    0.0928974 | sufficient     |
| Primeira Liga                 |     34 |           0.470588 |       -4.72 | -0.138824   |    1.90235 |    0.116294  | sufficient     |
| La Liga                       |     31 |           0.612903 |        3.47 |  0.111935   |    1.84387 |    0.0778065 | sufficient     |
| Copa Do Brasil                |     29 |           0.448276 |       -5.81 | -0.200345   |    1.89586 |    0.113241  | insufficient_n |
| Ligue 1                       |     29 |           0.62069  |        2.53 |  0.0872414  |    1.85483 |    0.068069  | insufficient_n |
| UEFA Europa League            |     21 |           0.428571 |       -6.88 | -0.327619   |    1.7181  |    0.11219   | insufficient_n |
| Premier League                |     19 |           0.578947 |       -0.77 | -0.0405263  |    1.91368 |    0.122737  | insufficient_n |
| League Cup                    |     18 |           0.555556 |       -0.72 | -0.04       |    1.83944 |    0.117556  | insufficient_n |
| UEFA Europa Conference League |     16 |           0.8125   |        6.69 |  0.418125   |    1.77438 |    0.1345    | insufficient_n |
| CONMEBOL Sudamericana         |     11 |           0.636364 |        1.71 |  0.155455   |    1.82909 |    0.134818  | insufficient_n |
| Super Cup                     |      7 |           0.714286 |        0.05 |  0.00714286 |    1.48571 |    0.0757143 | insufficient_n |
| US Open Cup                   |      4 |           0.5      |       -0.55 | -0.1375     |    1.9875  |    0.1685    | insufficient_n |
| Coppa Italia                  |      3 |           0        |       -3    | -1          |    1.74    |    0.0933333 | insufficient_n |
| UEFA Super Cup                |      3 |           1        |        1.99 |  0.663333   |    1.66333 |    0.0733333 | insufficient_n |
| DFB Pokal                     |      2 |           1        |        1.24 |  0.62       |    1.62    |    0.055     | insufficient_n |
| CONMEBOL Libertadores         |      1 |           1        |        0.95 |  0.95       |    1.95    |    0.104     | insufficient_n |
| Trophée des Champions         |      1 |           0        |       -1    | -1          |    1.73    |    0.038     | insufficient_n |

_Leagues with N < 30 marked insufficient for strong claims._

## 12. Candidate strategy (non-production hypothesis)

Markets: Over 2.5, Over 3.5, BTTS, Moneyline | Odds 1.90–2.50 | Calibrated EV 3–10%

### In-sample (all settled)

```json
{
  "bets": 110,
  "wins": 59,
  "losses": 51,
  "pushes": 0,
  "win_rate_ex_push": 0.5363636363636364,
  "average_odds": 2.0782727272727266,
  "total_stake_units": 110.0,
  "total_pnl": 11.79,
  "roi": 0.10718181818181817,
  "avg_profit_per_bet": 0.10718181818181817,
  "max_drawdown": -6.050000000000001,
  "profit_factor": 1.2311764705882355,
  "pnl_std": 1.040511634750765,
  "sharpe_like": 1.0803650388684196
}
```

### Out-of-sample (50/50 test, calibrated EV from train-only fit)

```json
{
  "bets": 18,
  "wins": 8,
  "losses": 10,
  "pushes": 0,
  "win_rate_ex_push": 0.4444444444444444,
  "average_odds": 2.1222222222222222,
  "total_stake_units": 18.0,
  "total_pnl": -0.6000000000000001,
  "roi": -0.03333333333333334,
  "avg_profit_per_bet": -0.03333333333333334,
  "max_drawdown": -4.0,
  "profit_factor": 0.9400000000000001,
  "pnl_std": 1.1128923630633405,
  "sharpe_like": -0.12707550247540023
}
```

## 13. Drawdown analysis

Baseline max drawdown (all settled): **-95.83000000000025** units
OOS walk-forward expanding max drawdown: **-79.20999999999995**

## 14. Statistical uncertainty

```json
{
  "oos_50_50_roi_bootstrap_mean": -0.06094224373576309,
  "oos_50_50_roi_95ci": [
    -0.12041059225512525,
    -0.0012041571753986368
  ],
  "oos_50_50_win_rate_95ci": [
    0.5189873417721519,
    0.5834292289988493
  ],
  "bootstrap_iterations": 2000
}
```

## 15. Overfitting risks

- Full-sample bin tables are descriptive only; strategy claims rely on OOS splits / walk-forward.
- Candidate filters were specified a priori; not grid-searched.
- Combination slices beyond listed hypotheses were not brute-forced.

## 16. Temporal stability (monthly, settled bets)

|   bets |   wins |   losses |   pushes |   win_rate_ex_push |   average_odds |   total_stake_units |   total_pnl |         roi |   avg_profit_per_bet |   max_drawdown |   profit_factor |   pnl_std |   sharpe_like | month   | strategy               |
|-------:|-------:|---------:|---------:|-------------------:|---------------:|--------------------:|------------:|------------:|---------------------:|---------------:|----------------:|----------:|--------------:|:--------|:-----------------------|
|    171 |     82 |       89 |        0 |           0.479532 |        1.78772 |                 171 |      -34.6  | -0.202339   |          -0.202339   |         -35.89 |        0.611236 |  0.878273 |     -3.01265  | 2026-07 | all_settled            |
|    895 |    535 |      360 |        0 |           0.597765 |        1.77797 |                 895 |        6.4  |  0.00715084 |           0.00715084 |         -37.86 |        1.01778  |  0.879568 |      0.24322  | 2026-08 | all_settled            |
|    680 |    363 |      317 |        0 |           0.533824 |        1.78735 |                 680 |      -63.05 | -0.0927206  |          -0.0927206  |         -66.01 |        0.801104 |  0.891611 |     -2.71178  | 2026-09 | all_settled            |
|    866 |    523 |      343 |        0 |           0.603926 |        1.77793 |                 866 |       15.74 |  0.0181755  |           0.0181755  |         -35.92 |        1.04589  |  0.879053 |      0.608458 | 2026-08 | walkforward_calibrated |
|    680 |    363 |      317 |        0 |           0.533824 |        1.78735 |                 680 |      -63.05 | -0.0927206  |          -0.0927206  |         -66.01 |        0.801104 |  0.891611 |     -2.71178  | 2026-09 | walkforward_calibrated |
|     11 |      4 |        7 |        0 |           0.363636 |        2.12545 |                  11 |       -2.17 | -0.197273   |          -0.197273   |          -5    |        0.69     |  1.11574  |     -0.586407 | 2026-07 | candidate_in_sample    |
|     66 |     39 |       27 |        0 |           0.590909 |        2.05455 |                  66 |       13.32 |  0.201818   |           0.201818   |          -5.9  |        1.49333  |  1.01435  |      1.61638  | 2026-08 | candidate_in_sample    |
|     33 |     16 |       17 |        0 |           0.484848 |        2.11    |                  33 |        0.64 |  0.0193939  |           0.0193939  |          -6.05 |        1.03765  |  1.07264  |      0.103865 | 2026-09 | candidate_in_sample    |
|      6 |      3 |        3 |        0 |           0.5      |        2.13333 |                   6 |        0.6  |  0.1        |           0.1        |          -2    |        1.2      |  1.2054   |      0.203209 | 2026-08 | candidate_oos          |
|     12 |      5 |        7 |        0 |           0.416667 |        2.11667 |                  12 |       -1.2  | -0.1        |          -0.1        |          -4    |        0.828571 |  1.11314  |     -0.3112   | 2026-09 | candidate_oos          |

## 17. Final research conclusions (direct answers)

1. **Is the raw model probability calibrated?**

No — full-sample ECE/Brier and bin-level errors show systematic miscalibration (ECE≈0.096). High predicted bins often underperform implied win rates.

2. **Does calibration materially improve probability estimates?**

OOS test-half metrics in JSON: raw Brier=0.2499, isotonic Brier=0.2399, Platt Brier=0.2395.

3. **Does calibrated EV predict realized ROI better than raw EV?**

Spearman(raw EV vs ROI)=-0.536, Spearman(calibrated EV vs ROI)=-0.250. Calibrated EV ordering aligns slightly better with realized ROI.

4. **Does higher calibrated EV correspond to better realized performance?**

Weak / inconsistent — inspect calibrated EV bucket table; high reported EV buckets often underperform.

5. **Which market types show the strongest out-of-sample evidence?**

[{'market': 'Draw', 'bets': 7, 'roi': 0.16142857142857142}, {'market': 'Double Chance X2', 'bets': 47, 'roi': 0.09170212765957445}, {'market': 'Over 3.5', 'bets': 69, 'roi': 0.004637681159420307}]

6. **Which market types show persistent negative performance?**

[{'market': 'Under 2.5', 'bets': 22, 'roi': -0.35636363636363644}, {'market': 'Team Over 1.5', 'bets': 93, 'roi': -0.23526881720430107}, {'market': 'Double Chance 1X', 'bets': 62, 'roi': -0.125}]

7. **Which odds ranges show the strongest out-of-sample performance?**

[{'odds_band': '2.10–2.50', 'bets': 101, 'roi': 0.14306930693069309}, {'odds_band': '1.90–2.10', 'bets': 122, 'roi': 0.009999999999999992}, {'odds_band': '1.30–1.50', 'bets': 125, 'roi': -0.032560000000000006}]

8. **Are the apparent league effects still present out-of-sample?**

[{'league': 'Serie A', 'bets': 64, 'roi': 0.21078124999999998}, {'league': 'Eredivisie', 'bets': 51, 'roi': 0.19686274509803928}, {'league': 'Liga MX', 'bets': 34, 'roi': 0.1585294117647059}] (sufficient-N leagues only; see league OOS table in JSON).

9. **Does the proposed 1.90–2.50 / 3–10% calibrated-EV candidate survive out-of-sample?**

Candidate OOS ROI=-0.0333 on 18 bets vs baseline-all OOS ROI=-0.0607. Shows higher OOS ROI but verify N and CI.

10. **What is the estimated out-of-sample ROI and uncertainty?**

OOS 50/50 ROI point estimate -0.0607; bootstrap 95% CI [-0.1204, -0.0012] on all OOS bets.

11. **What evidence supports or contradicts predictive value?**

Full-sample win rate 56.1% vs avg break-even implied 59.2%; settled ROI -0.0520. OOS bootstrap 95% CI for ROI excludes zero (negative), contradicting positive edge at flat 1u. Calibration improves probability scores but does not flip aggregate OOS profitability.

12. **What should we change BEFORE live deployment?**

Deploy calibration layer trained walk-forward; re-evaluate filters using calibrated EV; do not tighten filters on full-sample bins; collect holdout season before production changes.
