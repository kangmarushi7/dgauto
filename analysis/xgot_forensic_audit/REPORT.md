# xGOT Football Betting Strategy — Forensic Audit

**Date:** 2026-10-12  
**Scope:** Read-only audit of production `log_type=xgot` (paper research)  
**Primary evidence:** production Postgres `bet_entries` export (`xgot_bet_log_export.csv`, n=1109), source code, live DataGaffer `fixtures.json` sample  
**Window:** fixture dates 2026-10-04 → 2026-10-13; created_at 2026-10-04 → 2026-10-11  

---

## 1. Executive summary and confidence

| Question | Status | Finding |
|---|---|---|
| What is xGOT here? | **VERIFIED** | Provider field `sim_stats.projected_xg.xgot.{home,away,total}` from DataGaffer `fixtures.json`. This repo does **not** compute xGOT. |
| Historical inputs for picks? | **VERIFIED** | Current slate only: `matches` + `fixtures_by_id` + optional `heat_by_id`. No rolling lookback, no min-match gate in `xgot_strat`. |
| Exact strategy rules? | **VERIFIED** | Log-all eligible fixtures × markets. **No** xGOT/BC/Box/SOT/edge/EV filters at sync. Stake 1.0u paper. |
| Look-ahead / leakage? | **PARTIALLY VERIFIED** | Features are frozen on insert into `bet_entries`. `latest_data` is overwritten (no PIT archive). 23/1109 rows have `created_at` after kickoff. Cannot prove DG never revises projections. |
| Genuinely profitable? | **FAILED** (as market ROI) | Headline settled unit PnL **+5.28u / 1017** (ROI +0.52%) is **almost entirely SOT with null odds**, settled as synthetic even-money (+1/−1). Priced markets alone: **−44.72u / 819** (ROI **−5.46%**). |
| Worth further OOS testing? | **PARTIALLY VERIFIED** | Candidates exist (O2.5 @ xGOT 3.0–3.49; BTTS min(H,A) xGOT 1.2–1.49; SOT lines **only after** real odds). All are in-sample discoveries on ~8 days / 208 fixtures. |

**Confidence:** High on implementation and accounting; medium on point-in-time validity of DG projections; low that any filter is out-of-sample edge.

---

## 2. Repository map

| Path | Role | Active? |
|---|---|---|
| `app/xgot_strat.py` | Pick builder, sync, slice helper, enrich | **Production** |
| `app/scraper.py` | Pulls `https://www.datagaffer.com/fixtures.json` → `fixtures_by_id` | **Production** |
| `app/dg_feeds.py` | Extra feeds incl. `projected_heat_stats.json` → `heat_by_id` | **Production** |
| `app/fixture_refresh.py` | Scrape → save `latest_data` → `sync_all_strategy_bets` | **Production** |
| `app/bet_sync.py` | Auto-sync includes `xgot` | **Production** |
| `app/bet_scenarios.py` | `XGOT_BET_TYPE_MAP` resolve kinds | **Production** |
| `app/auto_resolve.py` | Settlement + `_compute_pnl` (SOT null-odds rule) | **Production** |
| `app/scheduler.py` | `run_all_auto_resolves` includes `xgot` | **Production** |
| `app/unified_bets.py` | Meta/labels for Today’s Bets / unified log | **Production** |
| `app/main.py` | `/xgot-strat`, `/xgot-bet-log`, APIs | **Production** |
| `templates/xgot_*.html` | UI + client-side slice filters | **Production** |
| `docs/superpowers/specs/2026-10-05-xgot-strategy-design.md` | Design spec | Docs |
| `tests/test_xgot_strat.py` | Unit tests | Tests |
| `app/strategy_buckets.py` | LIVE capital routing | **No xGOT** (paper only) |

---

## 3. Production execution path

```
POST /api/refresh  OR  scheduled fixture refresh
  → scrape_datagaffer_sync()          # app/scraper.py:122
       fixtures.json → fixtures_by_id (raw DG fixtures)
       fetch_extra_feeds()            # heat_by_id etc.
  → merge_outlooks → matches
  → save_state("latest_data", …)      # OVERWRITES prior slate
  → sync_all_strategy_bets(state)     # app/bet_sync.py
       → build_xgot_picks_from_state  # app/xgot_strat.py:323
       → sync_xgot_bets → insert_bets("xgot", …)
  → auto_resolve_open_bets("xgot")    # scheduler / API
       → resolve_kind_for_entry → _resolve_result → _compute_pnl
```

Manual: `POST /api/xgot-bet-log/sync`, bet-log UI sync/resync-today.

**Downstream of export:** `bet_entries` where `log_type='xgot'` is the canonical ledger; CSV export matches those columns + enrich labels.

---

## 4. xGOT data provenance and point-in-time validity

### 4.1 Definition in this system — VERIFIED

- **Source URL:** `https://www.datagaffer.com/fixtures.json` (`app/scraper.py:125–136`).
- **Path:** `fixtures_by_id[fid].sim_stats.projected_xg.xgot.{home,away,total}`.
- **Extraction:** `extract_projections()` (`app/xgot_strat.py:55–100`) — **read-only**; no formula in-repo.
- **Live check (2026-10-12):** 17/17 fixtures had `projected_xg.xgot` (e.g. home 1.56 / away 1.15 / total 2.71). Also present: `shots_on_target`, `shots_inside_box`, `big_chances_created`.
- **Home/away:** separate floats; total usually provided (else home+away).
- **Nature:** labeled `projected_*` / `sim_stats` on the pre-match fixture feed → treated as **pre-match projected match xGOT**, not post-match actuals. Provider methodology (rolling window, model, etc.) is **outside this repo** → **UNVERIFIED**.
- **Post-kickoff slate behaviour (live probe):** DG still exposes fractional `projected_xg.xgot` on fixtures after kickoff (no finished/status swap to actuals in this feed). Late sync can therefore still read projection-shaped fields, not confirmed final match xGOT — **PARTIALLY VERIFIED** risk for the 23 post-kickoff inserts.
- Provenance cross-check: [xGOT data provenance](9ba8468a-04e0-42d7-89d3-eead7f9ca2fb).

### 4.2 Related features

| Feature | Primary path | Fallback |
|---|---|---|
| Big chances | `sim_stats.big_chances_created` | heat `projected_stats.{home,away}.big_chances_created` (`projected_heat_stats.json`) |
| Box shots | `sim_stats.shots_inside_box` | none |
| SOT | `sim_stats.shots_on_target` | none |

Heat feed: `https://www.datagaffer.com/projected_heat_stats.json` (`app/dg_feeds.py:24,292–296`). Wired only as BC fallback in `extract_projections` when sim_stats BC sides are missing.

### 4.3 Timing / leakage tests

| Test | Result | Status |
|---|---|---|
| Features stored on bet row at sync? | Yes — `proj_*` columns on **first** insert only | **VERIFIED** |
| Re-sync updates `proj_*`? | No — `insert_bets` dedupe skips existing keys; projections not refreshed | **VERIFIED** |
| Historical projection archive? | No — `latest_data` fully replaced each refresh (`save_state`) | **VERIFIED** (gap) |
| Same-match final xGOT used for pick? | Code reads slate `sim_stats` at sync, not post-match accuracy feeds; DG may still serve projection-shaped fields after KO | **PARTIALLY VERIFIED** |
| Entry before kickoff? | 1086/1109 `created_at ≤ fixture_date`; **23 after** | **FAILED** for those 23 |
| Missing values | Eligible if xGOT total **or** (BC total **and** box total); SOT market skipped if SOT proj missing | **VERIFIED** |

**Point-in-time validity cannot be fully established** without immutable pre-match snapshots of `fixtures.json`. The only durable freeze of projections is the first `bet_entries` insert for that dedupe key.

---

## 5. Reconstructed strategy rules (as implemented)

### Pseudocode

```
for each match in slate with fixture_id:
  proj = extract_projections(fixtures_by_id[fid], heat=heat_by_id[fid])
  if not eligible(proj): continue   # xGOT total OR (BC and box)

  # Always attempt (skip if required odds missing, except SOT):
  add O2.5 if over_2_5_odds > 1
  add O3.5 if over_3_5_odds > 1
  add BTTS Yes if btts_yes_odds > 1
  line = max {L in {7.5,8.5,9.5,10.5} : L <= proj_sot_total}
  if line: add SOT Over line  # odds may be null
  fav = side with lower of home_ml_odds / away_ml_odds (skip equal)
  if fav odds: add ML on that team

  stake = 1.0 unit; status = open
  # NO xGOT threshold, percentile, league, EV, or sample-size filter
```

### Decision table

| Market | `bet_type` | Selection | Odds required | Resolve kind |
|---|---|---|---|---|
| Over 2.5 | `xgot_o25` | All eligible | yes (`over_2_5_odds`) | `over2.5` |
| Over 3.5 | `xgot_o35` | All eligible | yes | `over3.5` |
| BTTS Yes | `xgot_btts` | All eligible | yes | `btts` |
| SOT O{L} | `xgot_sot_o{75\|85\|95\|105}` | Nearest ladder line ≤ proj SOT | **no** (null OK) | `h2h_sot` |
| Favorite ML | `xgot_ml` | Lower 1X2 price H/A | yes | `moneyline` |

**UI-only filters** (do not change what was logged): percentile / min threshold / market on bet log (`select_fixture_ids_for_slice`, mirrored in JS).

**Capital:** paper only — not in `strategy_buckets` LIVE / Trade Picks.

---

## 6. Data schema ↔ export

Canonical table: `bet_entries` (`log_type='xgot'`).

Export: `analysis/xgot_forensic_audit/xgot_bet_log_export.csv` (production pull 2026-10-12).

| Field | Meaning |
|---|---|
| `fixture_id`, `fixture_date`, `fixture`, `home_team`, `away_team`, `league_name` | Match identity |
| `bet_type`, `team_name` | Market; ML team or SOT line |
| `odds`, `units`, `status`, `pnl_units` | Entry & settlement |
| `created_at`, `resolved_at` | Timestamps |
| `proj_xgot_*`, `proj_big_chances_*`, `proj_box_shots_*`, `proj_sot_*` | Snapshotted projections |

**CSV nature:** **live paper execution log** (not a retrospective backtest rebuild). Deduped by `(log_type, fixture_date, fixture, bet_type, team_name)`.

---

## 7. Settlement and PnL reconciliation

Settlement: `auto_resolve_open_bets("xgot")` → `resolve_kind_for_entry` → `_resolve_result` → `_compute_pnl` (`app/auto_resolve.py:443–454`).

```
won:  (odds-1)*units if odds>0 else +1.0*units   # ← critical for null-odds SOT
lost: -units
push: 0
```

**PnL mismatches vs recompute:** **0** (VERIFIED).

### Headline results (settled)

| Slice | N | Unit PnL | ROI |
|---|---:|---:|---:|
| All settled | 1017 | **+5.28** | +0.52% |
| Priced only (odds present) | 819 | **−44.72** | **−5.46%** |
| SOT (all null odds) | 198 | **+50.00** | +25.25% (synthetic 2.0) |
| Non-SOT | 819 | **−44.72** | −5.46% |

Max drawdown (settled chrono): **−65.69u**. Max losing streak: **21**.

### By market (settled)

| Market | Settled | W–L | Win% | Avg odds | Unit PnL | ROI |
|---|---:|---:|---:|---:|---:|---:|
| BTTS | 206 | 121–85 | 58.7% | 1.630 | −7.37 | −3.6% |
| ML | 201 | 110–91 | 54.7% | 1.913 | −1.80 | −0.9% |
| O2.5 | 206 | 124–82 | 60.2% | 1.639 | −5.45 | −2.6% |
| O3.5 | 206 | 72–134 | 35.0% | 2.561 | −30.10 | −14.6% |
| SOT O7.5 | 44 | 32–12 | 72.7% | **null** | +20.0 | n/a market |
| SOT O8.5 | 74 | 47–27 | 63.5% | **null** | +20.0 | n/a market |
| SOT O9.5 | 41 | 28–13 | 68.3% | **null** | +15.0 | n/a market |
| SOT O10.5 | 39 | 17–22 | 43.6% | **null** | −5.0 | n/a market |

**Overlapping selections:** up to **5 bets/fixture**; 208 unique settled fixtures. Fixture-level dependence is material.

---

## 8. Feature-bucket performance (in-sample only)

### O2.5 by total xGOT

| Bucket | N | Win% | Unit PnL | ROI | Avg odds |
|---|---:|---:|---:|---:|---:|
| 2.0–2.49 | 33 | 57.6% | +1.96 | +5.9% | 1.90 |
| 2.5–2.99 | 99 | 53.5% | −9.14 | −9.2% | 1.69 |
| **3.0–3.49** | **56** | **75.0%** | **+5.62** | **+10.0%** | **1.48** |
| 3.5–3.99 | 17 | 52.9% | −4.19 | −24.7% | 1.40 |

### O3.5 by total xGOT

| Bucket | N | Win% | Unit PnL | ROI |
|---|---:|---:|---:|---:|
| 2.0–2.49 | 33 | 33.3% | +1.32 | +4.0% |
| **2.5–2.99** | **99** | **27.3%** | **−27.75** | **−28.0%** |
| 3.0–3.49 | 56 | 48.2% | +1.20 | +2.1% |

### BTTS by min(home, away) xGOT (exploratory)

| min(H,A) | N | W–L | Unit PnL |
|---|---:|---:|---:|
| &lt;0.8 | 9 | 6–3 | +2.44 |
| 0.8–0.99 | 26 | 13–13 | −1.87 |
| 1.0–1.19 | 60 | 29–31 | −11.70 |
| **1.2–1.49** | **87** | **59–28** | **+7.69** |
| 1.5+ | 24 | 14–10 | −3.93 |

These buckets were **not** applied at sync; they are retrospective slices on the same sample used to observe them.

---

## 9. Leakage and backtest integrity

| Issue | Status | Notes |
|---|---|---|
| Post-match actuals as features | **PARTIALLY VERIFIED clean** | Code path uses slate projections at sync |
| No PIT projection store | **FAILED** for full auditability | Cannot replay historical sync state |
| Late sync after kickoff | **FAILED** for 23 rows | Contaminates “pre-match” claim for those |
| SOT null-odds PnL | **FAILED** as financial ROI | Synthetic +1u wins (`_compute_pnl`) |
| Multiple correlated bets/fixture | **VERIFIED** | Up to 5; independence violated |
| Walk-forward / OOS harness for xGOT | **UNVERIFIED / absent** | No xGOT backtest module |
| Survivorship | **PARTIALLY VERIFIED** | Log-all on scraped slate; leagues follow DG coverage |

**Insufficient for a valid chronological strategy test beyond ~8 days of paper log.** Do not manufacture a multi-season backtest from this ledger alone.

---

## 10. Candidate strategies (hypotheses only)

| # | Hypothesis | N (in-sample) | Confounders | Next evidence needed |
|---|---|---:|---|---|
| 1 | SOT O7.5/8.5/9.5 edge | 44/74/41 | **Null odds**; synthetic PnL | Book/exchange SOT prices at entry; reprice PnL |
| 2 | O2.5 when total xGOT ∈ [3.0, 3.49) | 56 | Short odds (~1.48); cherry-picked bucket | Chronological OOS; fixture-level bootstrap |
| 3 | BTTS when min(H,A) xGOT ∈ [1.2, 1.49) | 87 | In-sample search | Locked rule before next season block |
| 4 | Avoid O3.5 especially xGOT 2.5–2.99 | 99 | Large loss driver | Confirm in OOS before using as filter |
| 5 | Drop O3.5 entirely from log-all | 206 | Improves residual book | OOS vs goals-only basket |

**Do not** promote any candidate to LIVE from this sample.

---

## 11. Missing data / unresolved questions

1. DataGaffer definition of projected xGOT (training data, lookback, post-match overwrite policy).
2. Immutable pre-match snapshots of `fixtures.json` keyed by scrape time.
3. Real SOT market odds at entry (currently always null).
4. Commission / CLV / closing line vs entry.
5. Why 23 bets synced after kickoff (refresh lag vs timezone).
6. Financial stake mapping (paper units only; `STAKE_UNIT_INR` not applied to xGOT log).

---

## 12. Recommended next steps (ranked)

1. **Treat SOT unit PnL as invalid for ROI** until odds are attached; fix accounting display for null-odds wins.  
2. **Persist scrape snapshots** (`scraped_at` → immutable fixture JSON) for PIT audits.  
3. **Block or flag sync after kickoff** for research purity.  
4. **Freeze 1–2 candidate rules** (e.g. O2.5 & xGOT≥3.0; drop O3.5) and log a **separate** forward paper book.  
5. **Fixture-level metrics** (one observation per fixture per market family) for significance.  
6. Only after ≥several hundred OOS fixtures with priced markets, reconsider LIVE.

---

## Appendix A — Reproducible commands

```bash
# Inside dgauto container / app env against production DATABASE_URL:
XGOT_AUDIT_OUT=/tmp/xgot_audit_out PYTHONPATH=/app python /path/to/run_xgot_audit.py
# Outputs: summary.json, xgot_bet_log_export.csv
```

Local copies of this run:  
`analysis/xgot_forensic_audit/summary.json`  
`analysis/xgot_forensic_audit/xgot_bet_log_export.csv`

## Appendix B — Key code citations

- Extraction: `app/xgot_strat.py:55–100`  
- Eligibility / SOT line / build: `app/xgot_strat.py:166–320`  
- Sync: `app/xgot_strat.py:440–474`  
- Scrape: `app/scraper.py:122–170`  
- Refresh overwrite: `app/fixture_refresh.py:14–24`  
- Auto-sync hook: `app/bet_sync.py:67–84`  
- Resolve map: `app/bet_scenarios.py:161–170`  
- Null-odds win PnL: `app/auto_resolve.py:443–454`  
