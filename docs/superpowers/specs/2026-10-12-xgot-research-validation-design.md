# xGOT research validation + forward paper book

Date: 2026-10-12  
Status: Approved — implemented (research sync env-gated off by default; no LIVE)  
Depends on: `analysis/xgot_forensic_audit/REPORT.md`

## Goal

Harden research capture and run a **separate forward paper book** for frozen candidate rules, without changing the existing baseline xGOT pick generator or enabling LIVE capital.

## Locked decisions

| Topic | Choice |
|---|---|
| Baseline ledger | Keep `log_type=xgot` pick rules **unchanged** (log-all eligible × markets) |
| LIVE / Trade Picks | **Forbidden** for all xGOT variants |
| Forward candidates | Separate `log_type`s (or one research log + `variant_id`) — not in-place mutation of `xgot` |
| Threshold freeze | Candidates B/C frozen **before** forward collection; no retuning on the same period |
| Snapshots | Immutable DataGaffer `fixtures.json` blobs keyed by `scraped_at` (+ content hash) |
| Post-kickoff | Research syncs **reject** (default) or **flag** (baseline may flag-only first); document cause of historical 23 |
| SOT financial ROI | **Unavailable** until real entry odds exist; settlement outcome tracked separately |
| Reporting PnL | Actual decimal odds only; never treat null odds as 2.0 |

## Frozen candidate definitions (do not edit during forward test)

| ID | Name | Rule |
|---|---|---|
| **A** | Baseline | Current `build_xgot_picks` eligibility + markets (O2.5, O3.5, BTTS, SOT ladder, fav ML) |
| **B** | O2.5 xGOT[3.0,3.5) | Eligible fixture ∧ `3.0 ≤ proj_xgot_total < 3.5` ∧ market O2.5 only |
| **C** | BTTS minHA[1.2,1.5) | Eligible ∧ `1.2 ≤ min(proj_xgot_home, proj_xgot_away) < 1.5` ∧ BTTS only |
| **D** | No O3.5 | Same as A but **exclude** `xgot_o35` |
| **E** | SOT 7.5/8.5/9.5 | Same SOT line rule as A but only lines ∈ {7.5,8.5,9.5}; research-only; ROI gated on odds |

Strategy version string (example): `xgot-fw-2026-10-12.1` — bump on any rule/schema change.

## Non-goals

- Changing Main / H2H / Arahus / Trade Picks
- Claiming edge or promoting to LIVE
- Optimizing B/C thresholds on the forward window
- Backfilling multi-season history without snapshots

## Late-insert root cause (historical 23) — documented

All 23 post-kickoff rows share `created_at=2026-10-04T18:55:57Z` (first production sync after xGOT deploy). Lags 146–416 minutes. Cause: **inaugural sync with no kickoff guard** while DG still listed kicked-off fixtures on the slate. Not a recurring timezone bug in later days (0 late inserts after that batch in the audited export).

## Architecture

```
refresh scrape
  → write dg_fixture_snapshots(scraped_at, hash, fixtures.json)
  → save latest_data (as today)
  → sync baseline log_type=xgot (unchanged pick rules; optional late flag)
  → sync research variants A–E into isolated log_types
       each row: fixture_id, proj_*, odds, kickoff, created_at,
                 scrape_id, strategy_version, post_kickoff flag
  → resolve via existing auto_resolve (per log_type)
  → research report: outcome ≠ financial PnL; null-odds ROI = N/A
```

## SOT odds investigation (research track)

Priority order to document in implementation:

1. DataGaffer `all_odds.json` — search for SOT / shots_on_target markets (corners exist today; SOT may not).
2. Bookmaker APIs already in stack (if any) / API-Football odds endpoints.
3. Manual entry / pending-odds workflow (like H2H SOT today).

Until a source is verified, variant E records outcome only; financial columns stay null; reports mark ROI **unavailable**.

## Approval gate

Implement only after review of:

1. This design  
2. `docs/superpowers/plans/2026-10-12-xgot-research-validation.md`  
3. `analysis/xgot_forensic_audit/proposed_research_validation.diff.md` (proposed diff, not applied)
