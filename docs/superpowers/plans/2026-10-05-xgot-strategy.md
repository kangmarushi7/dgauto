# xGOT Strategy + Bet Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a paper-only `xgot` strategy that logs all projected slate fixtures across O2.5 / O3.5 / BTTS / SOT / favorite ML, with a bet log that slices by projection percentile after the fact.

**Architecture:** Mirror LM: `app/xgot_strat.py` builds picks from `fixtures_by_id[*].sim_stats`, syncs into `bet_entries` (`log_type=xgot`) with projection totals persisted on each row, pages/APIs under `/xgot-strat` and `/xgot-bet-log`, resolve via existing `auto_resolve_open_bets("xgot")`. Slice filters are client-side on the bet log.

**Tech Stack:** FastAPI, SQLAlchemy `bet_entries`, Jinja templates, shared `bet_log_date_filter.js`, unittest.

## Global Constraints

- Paper only — not LIVE / not Trade Picks v1
- No pre-filter at sync — log all fixtures with usable projections
- Markets: `xgot_o25`, `xgot_o35`, `xgot_btts`, `xgot_sot_o{75|85|95|105}`, `xgot_ml`
- Persist `fixture_id` + `proj_xgot_total` + `proj_big_chances_total` + `proj_box_shots_total` + `proj_sot_total` on `bet_entries`
- Spec: `docs/superpowers/specs/2026-10-05-xgot-strategy-design.md`

## File map

| File | Responsibility |
|---|---|
| `app/db.py` | New nullable columns + insert/list mapping |
| `app/xgot_strat.py` | Picks, sync, dashboard, market labels |
| `app/bet_scenarios.py` | xGOT bet_type → resolve/label map |
| `app/bet_sync.py` | Auto-sync hook |
| `app/unified_bets.py` | STRATEGY_META + LOG_TYPES + market label |
| `app/scheduler.py` | Include `xgot` in auto-resolve |
| `app/main.py` | Pages + API routes |
| `templates/xgot_strat.html` | Candidates UI |
| `templates/xgot_bet_log.html` | Log + slice panel + date filter |
| `templates/includes/app_nav.html` | Nav links |
| `tests/test_xgot_strat.py` | Unit tests |

---

### Task 1: Schema + projection helpers + pick builder

**Files:**
- Create: `app/xgot_strat.py`
- Modify: `app/db.py` (`bet_entries` columns, `insert_bets` / row dicts)
- Test: `tests/test_xgot_strat.py`

**Interfaces:**
- Produces: `extract_projections(fixture) -> dict`, `build_xgot_picks(matches, fixtures_by_id) -> list[dict]`, `LOG_TYPE = "xgot"`, `SOT_LINES = (7.5, 8.5, 9.5, 10.5)`

- [x] **Step 1: Write failing tests** for projection extract, eligibility, O2.5/O3.5/BTTS/ML/SOT line selection
- [x] **Step 2: Run tests — expect fail**
- [x] **Step 3: Add DB columns + migrate/create**; implement `xgot_strat` helpers + `build_xgot_picks` + `sync_xgot_bets`
- [x] **Step 4: Run tests — expect pass**
- [ ] **Step 5: Commit** `Add xGOT pick builder and bet_entries projection columns.` (await user request)

---

### Task 2: Resolve metadata + auto-resolve wiring

**Files:**
- Modify: `app/bet_scenarios.py` (XGOT_BET_TYPE_MAP + `scenario_meta_for_entry`)
- Modify: `app/scheduler.py` (`run_all_auto_resolves` include `xgot`)
- Modify: `app/unified_bets.py` (meta + market labels)
- Test: extend `tests/test_xgot_strat.py` for resolve kinds

- [x] **Step 1: Failing tests** for `resolve_kind_for_entry` on each `xgot_*` type
- [x] **Step 2: Implement map + wire scheduler/unified**
- [x] **Step 3: Tests pass** (commit await user request)

---

### Task 3: Sync hook + HTTP API + pages

**Files:**
- Modify: `app/bet_sync.py`, `app/main.py`
- Create: `templates/xgot_strat.html`, `templates/xgot_bet_log.html`
- Modify: `templates/includes/app_nav.html`

- [x] **Step 1: Add bet_sync entry** for `xgot`
- [x] **Step 2: Add main.py routes** mirroring LM (pages, GET/POST sync/resolve/auto-resolve/export)
- [x] **Step 3: Strat template** — table of fixtures + proj columns + markets
- [x] **Step 4: Bet log template** — date filter include + slice panel (rank/percentile/min/market) + stats + rows; wire `BetLogDateFilter.attach`
- [x] **Step 5: Nav links** under Strategies and Logs
- [x] **Step 6: Manual smoke** — sync against live state (102 picks / 22 fixtures)
- [ ] **Step 7: Commit** `Add xGOT strat/bet-log UI and APIs.` (await user request)

---

### Task 4: Slice helper tests + polish

**Files:**
- Optionally extract pure JS-testable logic; or Python helper `filter_xgot_entries(entries, *, rank_by, percentile, min_value, market)` used by API if needed — **v1 client-side only**, add a small Python helper duplicated for tests of percentile selection logic that the JS must match (document algorithm in comment).

- [x] **Step 1: Test percentile fixture selection** (top 10% of N fixtures, stable ties)
- [x] **Step 2: Implement `select_fixture_ids_for_slice` in `xgot_strat.py`**; mirrored in bet-log JS
- [ ] **Step 3: Commit** `Add xGOT bet-log slice selection helper.` (await user request)

---

### Task 5: Spec status + README note

- [x] Update spec status to Implemented (pending deploy)
- [x] Short README bullet under strategies
- [ ] Commit `Document xGOT paper strategy.` (await user request)

## Slice algorithm (JS + Python must match)

```
fixtures = unique by fixture_id (or fixture+date) among entries in date scope
sort fixtures by rank_metric desc, then fixture_id asc
keep ceil(n * pct) fixtures for Top 10/20/50%; All keeps all
optional: drop fixtures with rank_metric < min_value
entries kept if their fixture_id in kept set AND market filter matches
```

## Done when

- Sync inserts xgot rows with projection totals
- Bet log shows today by default, slices recompute stats
- Auto-resolve can settle goals/BTTS/ML/SOT for `log_type=xgot`
- Tests green for builder + resolve kinds + slice helper
