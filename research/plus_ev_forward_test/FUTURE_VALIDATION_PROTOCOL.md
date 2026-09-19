# Future validation protocol (Season 3)

## Freeze before Season 3

These rules are frozen. Do **not** change after viewing Season 3 outcomes.

1. Four independent portfolios only:
   - P1: odds in [2.10, 2.50] (all markets)
   - P2: Double Chance X2
   - P3: Over 3.5 (benchmark)
   - P4: Over 2.5 (benchmark)
2. Flat 1-unit stakes.
3. No EV-threshold search, no odds-band retuning, no league mining, no market combinations.
4. CLV only when closing odds captured; never fabricate.
5. Fair probability only via de-vig of full mutually exclusive outcome set.
6. Status labels and sample milestones as in `status.py` / README.

## Season 3 procedure

1. Keep Season 3 completely untouched until methodology freeze is confirmed.
2. Run live forward collector through Season 3 **or** ingest Season 3 signals with the same schema.
3. Evaluate exactly once:

```bash
python3 -m research.plus_ev_forward_test.run report
```

4. Compare Season 3 portfolio metrics to Season 2 seed / prior forward samples **without** changing portfolio definitions.
5. Do not promote any portfolio to production solely from ROI; require CLV + calibration + stability + adequate N.

## Production safety

- `research_only = true`
- `can_place_real_bet = false`
- No writes to production bet placement / sync / filters / Arahus.
