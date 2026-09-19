# Plus EV forward-test report

_Generated: 2026-09-19T05:13:18.761388+00:00_

**research_only = true** — no real bets placed by this module.

CLV requires closing_odds. Historical Season 2 seed rows have null closing odds. Live forward collector captures latest pre-kickoff odds going forward.

Total signals in ledger: **769**

## Portfolio comparison (independent hypotheses)

### Portfolio 1 — Odds 2.10–2.50

- Hypothesis: Qualifying bets priced 2.10–2.50 are repeatable
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
- ROI bootstrap 95% CI: {'mean': 0.020474669603524228, 'ci_low': -0.12190859030837009, 'ci_high': 0.17190859030837}

### Portfolio 2 — DC X2

- Hypothesis: Qualifying Double Chance X2 is repeatable
- Status: **NEGATIVE**
- Sample milestone: interesting (50–99)
- N settled: **65** (historical seed 70, live 0)
- W/L/P: 34/31/0
- Win rate: 0.5230769230769231
- Avg odds: 1.699846153846154
- P&L: -6.83u · ROI: -0.10507692307692308
- Max drawdown: -11.97
- Avg model p / raw EV: 0.6652793339768241 / 0.12158461538461537
- Avg calibrated p / EV: nan / nan
- Avg fair-market edge: None
- Mean/median CLV: None / None (n=0, pct+: None)
- ROI bootstrap 95% CI: {'mean': -0.10296538461538461, 'ci_low': -0.30246923076923077, 'ci_high': 0.10784999999999997}

### Portfolio 3 — Over 3.5 (benchmark)

- Hypothesis: Qualifying Over 3.5 is a useful benchmark/control
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
- ROI bootstrap 95% CI: {'mean': 0.05477161654135339, 'ci_low': -0.11776127819548872, 'ci_high': 0.2248947368421052}

### Portfolio 4 — Over 2.5 (benchmark)

- Hypothesis: Qualifying Over 2.5 is a useful benchmark/control
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
- ROI bootstrap 95% CI: {'mean': 0.0068080623306233075, 'ci_low': -0.07542276422764228, 'ci_high': 0.08899796747967481}

## Comparison answers

- **1_positive_clv**: ['none (or CLV unavailable)']
- **2_positive_roi**: ['Portfolio 1 — Odds 2.10–2.50', 'Portfolio 3 — Over 3.5 (benchmark)', 'Portfolio 4 — Over 2.5 (benchmark)']
- **3_positive_clv_and_roi**: ['none']
- **4_enough_sample_meaningful**: ['Portfolio 1 — Odds 2.10–2.50', 'Portfolio 3 — Over 3.5 (benchmark)', 'Portfolio 4 — Over 2.5 (benchmark)']
- **5_inconclusive**: ['Portfolio 1 — Odds 2.10–2.50', 'Portfolio 3 — Over 3.5 (benchmark)', 'Portfolio 4 — Over 2.5 (benchmark)']
- **6_evidence_better_prices_than_market**: Insufficient — closing odds not available on historical seed; await live forward CLV accumulation.

## Rules reminder

- Portfolios are FIXED. Do not combine or retune after seeing results.
- Do not declare proven profitable from small N.
- Positive CLV with negative ROI is still informative — report separately.
