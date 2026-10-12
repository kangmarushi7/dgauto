# Proposed implementation diff (REVIEW ONLY — not applied)

This document is the reviewable implementation sketch for  
`docs/superpowers/plans/2026-10-12-xgot-research-validation.md`.  
**No production files were modified for this proposal.**

---

## Diff summary

| Area | Action |
|---|---|
| `app/dg_snapshots.py` | **ADD** |
| `app/xgot_research.py` | **ADD** |
| `app/xgot_metrics.py` | **ADD** (optional pure helpers) |
| `app/db.py` | **ADD** table `dg_fixture_snapshots` + nullable bet metadata cols |
| `app/fixture_refresh.py` | **ADD** snapshot save call after scrape |
| `app/xgot_strat.py` | **ADD** timing helpers; annotate sync rows — **do not change** `build_xgot_picks` market rules |
| `app/bet_sync.py` | **ADD** env-gated research sync |
| `app/scheduler.py` | **ADD** research log_types to auto-resolve when enabled |
| `app/auto_resolve.py` | **NO CHANGE** in first PR (research reports ignore synthetic +1u) |
| `app/strategy_buckets.py` | **NO CHANGE** |
| `tests/test_dg_snapshots.py` | **ADD** |
| `tests/test_xgot_research.py` | **ADD** |
| `analysis/xgot_forward_paper/*` | **ADD** report runner + README |

---

## 1. `app/dg_snapshots.py` (new)

```python
"""Immutable DataGaffer fixtures.json snapshots for PIT research."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, Integer, MetaData, String, Table, Text, select
# Use shared engine/metadata from app.db — exact wiring in implementation.

def _canonical_bytes(fixtures: list) -> bytes:
    return json.dumps(fixtures, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def content_hash(fixtures: list) -> str:
    return hashlib.sha256(_canonical_bytes(fixtures)).hexdigest()

def save_fixtures_snapshot(*, scraped_at: str, fixtures: list) -> dict[str, Any]:
    """INSERT-only. Never updates an existing scraped_at row's payload."""
    ...
```

**Test:** mutate in-memory fixtures after save → stored payload unchanged; second save with different hash inserts new row.

---

## 2. `app/db.py` (additive)

```diff
+ dg_fixture_snapshots = Table(
+     "dg_fixture_snapshots",
+     metadata,
+     Column("id", String(64), primary_key=True),
+     Column("scraped_at", String(64), nullable=False, index=True),
+     Column("content_hash", String(64), nullable=False, index=True),
+     Column("fixture_count", Integer, nullable=False, default=0),
+     Column("payload", JSON, nullable=False),
+     Column("created_at", String(64), nullable=False),
+ )

  # on bet_entries (nullable):
+ Column("strategy_version", String(80)),
+ Column("scrape_id", String(64)),
+ Column("source_scraped_at", String(64)),
+ Column("post_kickoff", Boolean),
```

Extend `_ensure_bet_entries_columns()` accordingly.

---

## 3. `app/fixture_refresh.py` (hook)

```diff
   scraped = scrape_datagaffer_sync()
+  from app.dg_snapshots import save_fixtures_snapshot
+  snap = save_fixtures_snapshot(
+      scraped_at=scraped["scraped_at"],
+      fixtures=scraped.get("fixtures") or list((scraped.get("fixtures_by_id") or {}).values()),
+  )
   merged = merge_outlooks(...)
   state = {..., "last_snapshot_id": snap["id"]}
```

---

## 4. `app/xgot_strat.py` (helpers only — pick rules frozen)

```diff
+ def is_post_kickoff(fixture_date, *, now=None) -> bool: ...
+
  def sync_xgot_bets(picks, *, scraped_at=None, scrape_id=None):
      ...
+     post = is_post_kickoff(p.get("fixture_date"))
      candidates.append({
          ...
+         "strategy_version": "xgot-baseline-v1",
+         "scrape_id": scrape_id,
+         "source_scraped_at": scraped_at,
+         "post_kickoff": post,
      })
```

**Not in this diff:** any change to `is_eligible`, market loop, or SOT ladder.

---

## 5. `app/xgot_research.py` (new) — frozen variants

```python
XGOT_FW_VERSION = "xgot-fw-2026-10-12.1"

# B: 3.0 <= total < 3.5, O2.5 only
# C: 1.2 <= min(home,away) < 1.5, BTTS only
# D: baseline picks minus xgot_o35
# E: SOT lines in {7.5, 8.5, 9.5} only

LOG_TYPES = {
    "B": "xgot_fw_b",
    "C": "xgot_fw_c",
    "D": "xgot_fw_d",
    "E": "xgot_fw_e",
}

def filter_variant(variant_id: str, picks: list[dict]) -> list[dict]: ...

def sync_variant(variant_id: str, state: dict, *, allow_post_kickoff: bool = False) -> dict:
    picks = build_xgot_picks_from_state(state)  # unchanged builder
    picks = filter_variant(variant_id, picks)
    if not allow_post_kickoff:
        picks = [p for p in picks if not is_post_kickoff(p.get("fixture_date"))]
    # insert_bets(LOG_TYPES[variant_id], ...) with strategy_version=XGOT_FW_VERSION
```

---

## 6. `app/bet_sync.py` (env-gated)

```diff
+ XGOT_RESEARCH_SYNC_ENABLED = os.getenv("XGOT_RESEARCH_SYNC_ENABLED", "false").lower() in {"1","true","yes"}
  ...
  summary["xgot"] = _safe("xgot", lambda: sync_xgot_bets(...))  # unchanged
+ if XGOT_RESEARCH_SYNC_ENABLED:
+     from app.xgot_research import sync_all_research_variants
+     summary["xgot_research"] = _safe("xgot_research", lambda: sync_all_research_variants(state))
```

Default **off** so production behaviour is unchanged until explicitly enabled.

---

## 7. Metrics (research reports — not `_compute_pnl`)

```python
def financial_pnl(entry) -> float | None:
    odds = entry.get("odds")
    if odds is None or float(odds or 0) <= 1.0:
        return None  # NEVER treat as even money
    ...
```

Forward report marks variant E ROI as **unavailable** while `null_odds_settled == settled`.

---

## 8. Explicit non-diffs

```diff
# app/strategy_buckets.py — no xGOT
# app/trade_picks.py — no xGOT
# app/xgot_strat.build_xgot_picks — market selection unchanged
# app/auto_resolve._compute_pnl — deferred; global change needs separate approval
```

---

## 9. Late-insert finding (for implementers)

```
All 23 post-kickoff rows: created_at = 2026-10-04T18:55:57Z
Cause: first production sync after xGOT deploy; no kickoff guard.
Lag: 146–416 minutes. Later days in export: 0 late inserts.
```

---

## Approval checklist

- [ ] Design accepted (`docs/superpowers/specs/2026-10-12-xgot-research-validation-design.md`)
- [ ] Plan accepted (`docs/superpowers/plans/2026-10-12-xgot-research-validation.md`)
- [ ] This proposed diff accepted
- [ ] Decide: baseline post-kickoff = flag-only vs reject
- [ ] Decide: when to set `XGOT_RESEARCH_SYNC_ENABLED=true` on VPS
- [ ] Defer or schedule separate PR for `_compute_pnl` synthetic +1u

**Stop here until approved.** Do not merge/apply without an explicit go-ahead.