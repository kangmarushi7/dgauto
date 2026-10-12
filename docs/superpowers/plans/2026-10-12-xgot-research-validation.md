# xGOT Research Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add immutable DG fixture snapshots, kickoff-safe research capture, honest SOT accounting, and a separate forward paper book for frozen candidates A–E — without changing baseline `log_type=xgot` pick rules or enabling LIVE.

**Architecture:** Keep `app/xgot_strat.py` baseline builder intact. Add `app/dg_snapshots.py` (immutable scrape archive), `app/xgot_research.py` (frozen variants + sync + metrics that refuse null-odds ROI), optional schema columns / new `log_type`s for research ledgers, reporting under `analysis/xgot_forward_paper/`. Wire snapshot write into `fixture_refresh` / scrape path. Do **not** add xGOT to `strategy_buckets`.

**Tech Stack:** FastAPI app, SQLAlchemy/`bet_entries` + new snapshot table, unittest, existing `auto_resolve`.

## Global Constraints

- Do **not** modify baseline pick-generation rules in `build_xgot_picks` eligibility/markets.
- Do **not** route any xGOT variant into LIVE / Trade Picks / `strategy_buckets`.
- Preserve existing `log_type=xgot` ledger for comparison.
- Candidate thresholds B/C are frozen in `docs/superpowers/specs/2026-10-12-xgot-research-validation-design.md` — no retune on forward window.
- Null odds ⇒ financial ROI unavailable (never synthetic 2.0 in research reports).
- Strategy version constant: `XGOT_FW_VERSION = "xgot-fw-2026-10-12.1"`.

## File map

| File | Responsibility |
|---|---|
| `app/dg_snapshots.py` | Persist/load immutable `fixtures.json` snapshots |
| `app/db.py` | `dg_fixture_snapshots` table + ensure columns / research metadata cols |
| `app/fixture_refresh.py` / `app/scraper.py` | Call snapshot save after successful scrape |
| `app/xgot_research.py` | Frozen variants A–E, kickoff guard, research sync, metrics |
| `app/bet_sync.py` | Optional hook to sync research variants (env-gated) |
| `app/scheduler.py` | Include research log_types in auto-resolve if enabled |
| `app/bet_scenarios.py` | Resolve maps for new research bet_types if needed (reuse xgot_* kinds) |
| `app/auto_resolve.py` | **Do not** change global null-odds +1u for all logs in v1; research **reporting** ignores it. Optional: gate synthetic win PnL behind log_type allowlist (review separately — production-facing). |
| `analysis/xgot_forward_paper/run_report.py` | Dated forward report generator |
| `tests/test_dg_snapshots.py` | Immutability / hash tests |
| `tests/test_xgot_research.py` | Kickoff guard, variants, PnL/odds validation |
| `templates/` | Optional research dashboard later — **out of scope for first PR** unless trivial |

---

### Task 1: Spec freeze + late-insert note (docs only)

**Files:** design already at `docs/superpowers/specs/2026-10-12-xgot-research-validation-design.md`

- [x] Confirm candidate table A–E matches audit recommendations
- [x] Record late-insert cause (2026-10-04T18:55:57Z inaugural sync) in design § Late-insert
- [ ] Commit docs only after user approval of this plan

---

### Task 2: Immutable DG fixture snapshots

**Files:**
- Create: `app/dg_snapshots.py`
- Modify: `app/db.py`, `app/fixture_refresh.py` (or scraper return path)
- Test: `tests/test_dg_snapshots.py`

**Schema (`dg_fixture_snapshots`):**

```
id PK
scraped_at String indexed
content_hash String(64)  # sha256 of canonical JSON bytes
fixture_count Integer
payload JSON             # full fixtures list (or compressed externally later)
created_at String
UniqueConstraint(scraped_at) or allow multiple with unique (scraped_at, content_hash)
```

**API:**

```python
def save_fixtures_snapshot(*, scraped_at: str, fixtures: list) -> dict
def get_snapshot(snapshot_id|scraped_at) -> dict | None
```

Behaviour:
- Insert-only; never UPDATE payload
- Same content_hash within short window may skip duplicate insert (optional)
- Return `{id, scraped_at, content_hash, fixture_count}`

- [x] **Step 1: Failing test** — save twice with same payload does not mutate first row; second scrape with different payload inserts new row
- [x] **Step 2: Implement table + save/get**
- [x] **Step 3: Hook into refresh after scrape** (before or after `save_state`)
- [x] **Step 4: Tests pass**
- [ ] **Step 5: Commit** `Add immutable DataGaffer fixtures.json snapshots.`

---

### Task 3: Kickoff guard + research row metadata (baseline-safe)

**Files:**
- Modify: `app/xgot_strat.py` (additive helpers only — **do not change market selection rules**)
- Modify: `app/db.py` nullable columns on `bet_entries`: `strategy_version`, `scrape_id`, `source_scraped_at`, `post_kickoff` (Boolean)
- Test: extend `tests/test_xgot_strat.py` or new file

**Helpers (pure):**

```python
def is_post_kickoff(fixture_date, *, now=None) -> bool
def annotate_pick_timing(pick, *, scraped_at, scrape_id, strategy_version, now=None) -> dict
```

**Baseline sync policy (v1 recommendation for review):**
- Still insert baseline picks (preserve universe log)
- Set `post_kickoff=True` when `created_at > fixture_date`
- Research variants (Task 4): **skip** post-kickoff by default (`XGOT_RESEARCH_ALLOW_POST_KICKOFF=false`)

- [x] Failing tests for guard / annotation
- [x] Implement + migrate columns
- [x] Wire annotate into `sync_xgot_bets` without changing which markets are built
- [ ] Commit `Flag post-kickoff xGOT inserts and attach scrape metadata.`

---

### Task 4: Frozen research variants A–E + isolated sync

**Files:**
- Create: `app/xgot_research.py`
- Modify: `app/bet_sync.py` (env `XGOT_RESEARCH_SYNC_ENABLED`, default **false** until approved)
- Modify: `app/scheduler.py` resolve list for new log_types when enabled
- Modify: `app/bet_scenarios.py` if new bet_types needed (prefer reuse `xgot_*` types under distinct `log_type`)

**log_type map (proposed):**

| Variant | `log_type` |
|---|---|
| A mirror (optional; or reuse `xgot`) | `xgot` is baseline — do not duplicate unless needed for identical schema |
| B | `xgot_fw_b` |
| C | `xgot_fw_c` |
| D | `xgot_fw_d` |
| E | `xgot_fw_e` |

**Interfaces:**

```python
XGOT_FW_VERSION = "xgot-fw-2026-10-12.1"
VARIANTS: dict[str, Callable[[list[dict]], list[dict]]]

def build_variant_picks(variant_id, state, *, now=None) -> list[dict]
def sync_variant(variant_id, state) -> dict  # respects kickoff reject
def sync_all_research_variants(state) -> dict
```

Variant filters operate on picks from **unchanged** `build_xgot_picks_from_state` (filter/transform only).

- [x] Failing tests for B/C/D/E selection counts on fixture fixtures
- [x] Implement builders + sync
- [x] Env-gate bet_sync / resolve
- [ ] Commit `Add frozen xGOT forward-paper research variants (env-gated).`

---

### Task 5: Honest metrics + forward report

**Files:**
- Create: `analysis/xgot_forward_paper/run_report.py`
- Create: `analysis/xgot_forward_paper/README.md`
- Optional: `app/xgot_metrics.py` pure functions used by report + tests

**Rules:**

```python
def financial_pnl(entry) -> float | None:
    # None if odds missing/invalid; never +1u synthetic
def outcome_stats(entries) -> dict  # W/L/P regardless of odds
def financial_stats(entries) -> dict  # only priced settled; ROI N/A if empty
def fixture_cluster_note(entries) -> dict  # unique fixtures, max bets/fixture
```

Report outputs dated markdown + JSON under `analysis/xgot_forward_paper/output/`.

Per variant: placed, settled, unique fixtures, win rate (outcome), avg entry odds (priced), turnover, net PnL, ROI, drawdown, losing streak; compare to baseline; note correlated bets.

- [x] Tests: null-odds win ⇒ financial_pnl is None; priced win matches (O-1)*S
- [x] Implement report CLI
- [ ] Commit `Add xGOT forward-paper metrics and report runner.`

---

### Task 6: SOT odds source investigation (write-up, not LIVE)

**Files:** `analysis/xgot_forward_paper/sot_odds_sources.md`

Probe (read-only):
1. Sample `all_odds.json` for SOT keys
2. Note H2H comment that SOT is manual / not on Polymarket
3. Recommend next integration or explicit pending-odds workflow

- [x] Document findings + recommendation
- [ ] Commit `Document SOT odds source options for xGOT research.`

---

### Task 7: Validation suite + deploy checklist

- [x] `unittest` for snapshots, kickoff, variants, metrics
- [x] Manual: refresh writes snapshot; research sync off by default; baseline still inserts
- [x] Deploy checklist: enable `XGOT_RESEARCH_SYNC_ENABLED` only after approval; never enable LIVE
- [ ] First forward-paper report dated with `XGOT_FW_VERSION` (run after deploy has data)

---

## Production-facing behaviour (explicit)

| Change | Production-facing? | When |
|---|---|---|
| Snapshot writes on refresh | Yes (additive storage) | After approval |
| Baseline pick rules | **No change** | — |
| `post_kickoff` flag on baseline sync | Mild (metadata) | After approval |
| Research variant sync | Yes but env-gated default off | After approval |
| Changing `_compute_pnl` null-odds +1u | **Yes — global** | Separate review; prefer research reporting first |
| strategy_buckets / Trade Picks | **Never** in this plan | — |

## Done when

- Snapshots immutable and tested
- Late syncs flagged/rejected per policy
- Research variants sync env-gated with frozen rules
- Reports never invent SOT ROI without odds
- Baseline `xgot` universe log still running unchanged
- No LIVE routing
