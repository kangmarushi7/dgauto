# Plus EV forward-test report

_Generated: 2026-09-19T05:01:18.485413+00:00_

**research_only = true** — no real bets placed by this module.

CLV requires closing_odds. Historical Season 2 seed rows have null closing odds. Live forward collector captures latest pre-kickoff odds going forward.

Total signals in ledger: **805**

## Portfolio comparison (independent hypotheses)

### Portfolio A — Over 3.5

- Hypothesis: H1: Over 3.5 is profitable/repeatable
- Status: **PROMISING — NEEDS MORE DATA**
- Sample milestone: meaningful (100–249)
- N settled: **133** (historical seed 148, live 0)
- W/L/P: 69/64/0
- Win rate: 0.518796992481203
- Avg odds: 2.077443609022556
- P&L: 7.390000000000001u · ROI: 0.05556390977443609
- Max drawdown: -10.750000000000002
- Avg model p / raw EV: 0.573481944340629 / 0.17878195488721804
- Avg calibrated p / EV: nan / nan
- Avg fair-market edge: None
- Mean/median CLV: None / None (n=0, pct+: None)
- ROI bootstrap 95% CI: {'mean': 0.05695609022556392, 'ci_low': -0.12204135338345866, 'ci_high': 0.22738345864661644}

### Portfolio B — Over 2.5

- Hypothesis: H2: Over 2.5 is profitable/repeatable
- Status: **PROMISING — NEEDS MORE DATA**
- Sample milestone: strong forward-test sample building (250–499)
- N settled: **369** (historical seed 399, live 0)
- W/L/P: 228/139/2
- Win rate: 0.6212534059945504
- Avg odds: 1.6379403794037943
- P&L: 2.230000000000002u · ROI: 0.006043360433604342
- Max drawdown: -17.589999999999996
- Avg model p / raw EV: 0.681355471825929 / 0.10200271002710026
- Avg calibrated p / EV: nan / nan
- Avg fair-market edge: None
- Mean/median CLV: None / None (n=0, pct+: None)
- ROI bootstrap 95% CI: {'mean': 0.005868008130081302, 'ci_low': -0.07781029810298101, 'ci_high': 0.08620731707317073}

### Portfolio C — Serie A

- Hypothesis: H3: Serie A has better model performance
- Status: **PROMISING — NEEDS MORE DATA**
- Sample milestone: meaningful (100–249)
- N settled: **143** (historical seed 145, live 0)
- W/L/P: 88/55/0
- Win rate: 0.6153846153846154
- Avg odds: 1.8609090909090906
- P&L: 16.689999999999998u · ROI: 0.11671328671328669
- Max drawdown: -11.760000000000003
- Avg model p / raw EV: 0.6272110377128877 / 0.1227762237762238
- Avg calibrated p / EV: nan / nan
- Avg fair-market edge: None
- Mean/median CLV: None / None (n=0, pct+: None)
- ROI bootstrap 95% CI: {'mean': 0.11896797202797202, 'ci_low': -0.030989510489510475, 'ci_high': 0.274055944055944}

### Portfolio D — Odds 2.10–2.50

- Hypothesis: H4: Odds 2.10–2.50 have better model performance
- Status: **PROMISING — NEEDS MORE DATA**
- Sample milestone: meaningful (100–249)
- N settled: **227** (historical seed 249, live 0)
- W/L/P: 103/124/0
- Win rate: 0.45374449339207046
- Avg odds: 2.2465198237885464
- P&L: 4.280000000000003u · ROI: 0.018854625550660805
- Max drawdown: -24.27
- Avg model p / raw EV: 0.5364101538915182 / 0.20255506607929516
- Avg calibrated p / EV: nan / nan
- Avg fair-market edge: None
- Mean/median CLV: None / None (n=0, pct+: None)
- ROI bootstrap 95% CI: {'mean': 0.022239559471365637, 'ci_low': -0.12064757709251103, 'ci_high': 0.16749449339207043}

## Comparison answers

- **1_positive_clv**: ['none (or CLV unavailable)']
- **2_positive_roi**: ['Portfolio A — Over 3.5', 'Portfolio B — Over 2.5', 'Portfolio C — Serie A', 'Portfolio D — Odds 2.10–2.50']
- **3_positive_clv_and_roi**: ['none']
- **4_enough_sample_meaningful**: ['Portfolio A — Over 3.5', 'Portfolio B — Over 2.5', 'Portfolio C — Serie A', 'Portfolio D — Odds 2.10–2.50']
- **5_inconclusive**: ['Portfolio A — Over 3.5', 'Portfolio B — Over 2.5', 'Portfolio C — Serie A', 'Portfolio D — Odds 2.10–2.50']
- **6_evidence_better_prices_than_market**: Insufficient — closing odds not available on historical seed; await live forward CLV accumulation.

## Rules reminder

- Portfolios are FIXED. Do not combine or retune after seeing results.
- Do not declare proven profitable from small N.
- Positive CLV with negative ROI is still informative — report separately.
