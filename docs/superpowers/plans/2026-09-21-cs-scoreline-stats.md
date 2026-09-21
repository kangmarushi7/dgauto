# Correct Score Scoreline Leg Stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show settled leg-level won/lost/push/PnL/ROI broken down by scoreline on the Correct Score Bet Log page.

**Architecture:** Add `scoreline_leg_stats(entries)` in `app/correct_score_strat.py`, attach as `dashboard["by_scoreline"]` from `correct_score_dashboard()`, and render a **Scoreline performance** table in `templates/cs_bet_log.html` under Basket Performance. No new API routes — page and `GET /api/correct-score-bet-log` already return `dashboard`.

**Tech Stack:** Python 3 / FastAPI / Jinja templates / unittest

## Global Constraints

- Aggregation: leg-level by scoreline (`team_name`, e.g. `"2-1"`)
- Settlement filter: settled only (`won` / `lost` / `push`) for counts, PnL, ROI
- ROI: `pnl_units / staked_units` for that scoreline (settled stake only)
- Season: inherit existing page/API season filter
- Sort: settled N descending, then scoreline ascending
- No CSV export, min-N filter, or basket-hit-only view in v1
- Spec: `docs/superpowers/specs/2026-09-21-cs-scoreline-stats-design.md`

## File Structure

| File | Responsibility |
|------|----------------|
| `app/correct_score_strat.py` | `scoreline_leg_stats()` + wire into `correct_score_dashboard()` |
| `tests/test_correct_score_strat.py` | Unit tests for scoreline aggregation |
| `templates/cs_bet_log.html` | Scoreline performance table + `renderScorelines()` |

---

### Task 1: `scoreline_leg_stats` + dashboard wire-up (TDD)

**Files:**
- Modify: `app/correct_score_strat.py` (add function near `correct_score_dashboard`, ~line 521)
- Modify: `tests/test_correct_score_strat.py` (import + new `ScorelineLegStatsTests`)
- Test: `tests/test_correct_score_strat.py`

**Interfaces:**
- Consumes: entry dicts with `team_name`, `status`, `units`, `pnl_units`, `odds`; helpers `_num`, `compute_bet_stats` patterns / `_avg_odds` via local odds mean
- Produces: `scoreline_leg_stats(entries: list[dict[str, Any]]) -> list[dict[str, Any]]` where each dict has:
  - `scoreline: str`
  - `settled: int`
  - `won: int`, `lost: int`, `push: int`
  - `win_pct: float` (won/(won+lost)*100 when decided else `0.0`)
  - `staked_units: float`
  - `pnl_units: float`
  - `roi_pct: float` (pnl/staked*100 when staked else `0.0`)
  - `avg_odds: float | None`
- Also: `correct_score_dashboard(...)` includes `"by_scoreline": scoreline_leg_stats(entries)`

- [ ] **Step 1: Write the failing tests**

Add import of `scoreline_leg_stats` and `correct_score_dashboard` to `tests/test_correct_score_strat.py`, then append:

```python
class ScorelineLegStatsTests(unittest.TestCase):
    ENTRIES = [
        {
            "team_name": "2-1",
            "status": "won",
            "units": 0.5,
            "pnl_units": 4.5,
            "odds": 10.0,
        },
        {
            "team_name": "2-1",
            "status": "lost",
            "units": 0.5,
            "pnl_units": -0.5,
            "odds": 10.0,
        },
        {
            "team_name": "1-0",
            "status": "lost",
            "units": 1.0,
            "pnl_units": -1.0,
            "odds": 8.0,
        },
        {
            "team_name": "1-0",
            "status": "push",
            "units": 1.0,
            "pnl_units": 0.0,
            "odds": 8.0,
        },
        {
            "team_name": "2-1",
            "status": "open",
            "units": 0.5,
            "pnl_units": None,
            "odds": 10.0,
        },
        {
            "team_name": " 3-0 ",
            "status": "won",
            "units": 0.2,
            "pnl_units": 1.8,
            "odds": 10.0,
        },
        {
            "team_name": "",
            "status": "won",
            "units": 1.0,
            "pnl_units": 2.0,
            "odds": 3.0,
        },
    ]

    def test_groups_settled_legs_by_scoreline(self):
        rows = scoreline_leg_stats(self.ENTRIES)
        by = {r["scoreline"]: r for r in rows}
        self.assertEqual(set(by), {"2-1", "1-0", "3-0"})

        two_one = by["2-1"]
        self.assertEqual(two_one["settled"], 2)
        self.assertEqual(two_one["won"], 1)
        self.assertEqual(two_one["lost"], 1)
        self.assertEqual(two_one["push"], 0)
        self.assertEqual(two_one["win_pct"], 50.0)
        self.assertEqual(two_one["staked_units"], 1.0)
        self.assertEqual(two_one["pnl_units"], 4.0)
        self.assertEqual(two_one["roi_pct"], 400.0)
        self.assertEqual(two_one["avg_odds"], 10.0)

        one_zero = by["1-0"]
        self.assertEqual(one_zero["settled"], 2)
        self.assertEqual(one_zero["won"], 0)
        self.assertEqual(one_zero["lost"], 1)
        self.assertEqual(one_zero["push"], 1)
        self.assertEqual(one_zero["win_pct"], 0.0)
        self.assertEqual(one_zero["staked_units"], 2.0)
        self.assertEqual(one_zero["pnl_units"], -1.0)
        self.assertEqual(one_zero["roi_pct"], -50.0)

    def test_open_legs_ignored(self):
        rows = scoreline_leg_stats(
            [{"team_name": "0-0", "status": "open", "units": 1.0, "pnl_units": None, "odds": 5.0}]
        )
        self.assertEqual(rows, [])

    def test_empty_input(self):
        self.assertEqual(scoreline_leg_stats([]), [])

    def test_sort_by_settled_desc_then_scoreline(self):
        rows = scoreline_leg_stats(self.ENTRIES)
        self.assertEqual([r["scoreline"] for r in rows], ["1-0", "2-1", "3-0"])

    def test_dashboard_includes_by_scoreline(self):
        dash = correct_score_dashboard(self.ENTRIES)
        self.assertIn("by_scoreline", dash)
        self.assertEqual(len(dash["by_scoreline"]), 3)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_correct_score_strat.ScorelineLegStatsTests -v`

Expected: FAIL with `ImportError` / `AttributeError` for `scoreline_leg_stats`

- [ ] **Step 3: Implement `scoreline_leg_stats` and wire dashboard**

In `app/correct_score_strat.py`, add above `correct_score_dashboard`:

```python
def scoreline_leg_stats(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Settled leg performance grouped by scoreline (`team_name`)."""
    settled_statuses = {"won", "lost", "push"}
    buckets: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        status = str(entry.get("status") or "").strip().lower()
        if status not in settled_statuses:
            continue
        scoreline = str(entry.get("team_name") or "").strip()
        if not scoreline:
            continue
        buckets.setdefault(scoreline, []).append(entry)

    rows: list[dict[str, Any]] = []
    for scoreline, legs in buckets.items():
        won = sum(1 for e in legs if str(e.get("status") or "").lower() == "won")
        lost = sum(1 for e in legs if str(e.get("status") or "").lower() == "lost")
        push = sum(1 for e in legs if str(e.get("status") or "").lower() == "push")
        decided = won + lost
        staked = round(sum(_num(e.get("units")) or 0.0 for e in legs), 3)
        pnl = round(sum(_num(e.get("pnl_units")) or 0.0 for e in legs), 3)
        odds_vals = [_num(e.get("odds")) for e in legs if _num(e.get("odds"))]
        rows.append(
            {
                "scoreline": scoreline,
                "settled": len(legs),
                "won": won,
                "lost": lost,
                "push": push,
                "win_pct": round(100.0 * won / decided, 1) if decided else 0.0,
                "staked_units": staked,
                "pnl_units": pnl,
                "roi_pct": round(100.0 * pnl / staked, 1) if staked else 0.0,
                "avg_odds": round(sum(odds_vals) / len(odds_vals), 2) if odds_vals else None,
            }
        )
    rows.sort(key=lambda r: (-r["settled"], r["scoreline"]))
    return rows
```

Update `correct_score_dashboard` return to include:

```python
        "by_scoreline": scoreline_leg_stats(entries),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_correct_score_strat.ScorelineLegStatsTests -v`

Expected: all PASS

Also: `python -m unittest tests.test_correct_score_strat -v` — full file still PASS

- [ ] **Step 5: Commit**

```bash
git add app/correct_score_strat.py tests/test_correct_score_strat.py
git commit -m "Add settled scoreline leg stats to Correct Score dashboard."
```

---

### Task 2: Scoreline performance UI on CS bet log

**Files:**
- Modify: `templates/cs_bet_log.html`

**Interfaces:**
- Consumes: `dashboard.by_scoreline` from Task 1 (`scoreline`, `settled`, `won`, `lost`, `push`, `win_pct`, `pnl_units`, `roi_pct`, `avg_odds`)
- Produces: visible table under Basket Performance; refreshed via `renderAll`

- [ ] **Step 1: Add section markup after Basket Performance**

Insert after the Basket Performance `</section>` (after line ~39), before Baskets:

```html
      <section class="recommendation-card">
        <h2>Scoreline performance</h2>
        <p class="hit-note" id="scorelineEmpty" hidden>No settled scoreline legs yet.</p>
        <table data-column-filters="1" data-csv-export="1" data-csv-filename="cs-scoreline-stats">
          <thead>
            <tr>
              <th>Score</th>
              <th>Settled</th>
              <th>Won</th>
              <th>Lost</th>
              <th>Push</th>
              <th>Win%</th>
              <th>PnL(u)</th>
              <th>ROI%</th>
              <th>Avg odds</th>
            </tr>
          </thead>
          <tbody id="scorelineRows"></tbody>
        </table>
      </section>
```

- [ ] **Step 2: Wire JS render**

Near other element refs:

```javascript
      const scorelineRowsEl = document.getElementById("scorelineRows");
      const scorelineEmptyEl = document.getElementById("scorelineEmpty");
```

Add `renderScorelines` and call it from `renderStats` or `renderAll`:

```javascript
      function toneClass(n) {
        if (n == null || Number.isNaN(Number(n)) || Number(n) === 0) return null;
        return Number(n) > 0 ? "cs-pos" : "cs-neg";
      }

      function renderScorelines(rows) {
        const list = rows || [];
        scorelineRowsEl.innerHTML = "";
        scorelineEmptyEl.hidden = list.length > 0;
        scorelineRowsEl.closest("table").hidden = list.length === 0;
        if (!list.length) return;
        for (const r of list) {
          const tr = document.createElement("tr");
          tr.appendChild(td(r.scoreline, "cs-score"));
          tr.appendChild(td(r.settled));
          tr.appendChild(td(r.won));
          tr.appendChild(td(r.lost));
          tr.appendChild(td(r.push));
          tr.appendChild(td(r.win_pct != null ? Number(r.win_pct).toFixed(1) : "—"));
          tr.appendChild(td(r.pnl_units, toneClass(r.pnl_units)));
          tr.appendChild(
            td(r.roi_pct != null ? `${Number(r.roi_pct).toFixed(1)}%` : "—", toneClass(r.roi_pct))
          );
          tr.appendChild(td(r.avg_odds != null ? Number(r.avg_odds).toFixed(2) : "—"));
          scorelineRowsEl.appendChild(tr);
        }
        if (window.TableTools) window.TableTools.reapply(scorelineRowsEl.closest("table"));
      }
```

Update `renderAll`:

```javascript
      function renderAll(payload) {
        const dash = payload.dashboard || {};
        renderStats(dash);
        renderScorelines(dash.by_scoreline || []);
        renderBaskets(payload.baskets || []);
        renderLegs(payload.entries || []);
      }
```

Ensure the initial page boot path that calls `renderAll` / `renderStats` still works (same as today — typically `renderAll({...})` with server-injected payload or fetch). If the template currently calls `renderStats` + `renderBaskets` + `renderLegs` separately on load, add `renderScorelines` there too.

- [ ] **Step 3: Manual smoke**

Run app locally (or hit deployed after later deploy): open `/correct-score-bet-log`, confirm Scoreline performance table appears under Basket Performance with columns filled for settled scorelines; sync/auto-resolve still refresh stats.

- [ ] **Step 4: Commit**

```bash
git add templates/cs_bet_log.html
git commit -m "Show scoreline performance table on Correct Score bet log."
```

---

## Spec coverage (self-review)

| Spec requirement | Task |
|---|---|
| Leg-level by scoreline | Task 1 |
| Settled only | Task 1 |
| Won/Lost/Push/PnL/ROI/Avg odds | Task 1 + Task 2 columns |
| `dashboard.by_scoreline` | Task 1 |
| Table under Basket Performance | Task 2 |
| Season filter via existing payload | No extra work (entries already filtered) |
| Sort settled desc, scoreline asc | Task 1 |
| Unit tests | Task 1 |
| Non-goals (CSV API, basket-hit, open in ROI) | Intentionally omitted |

## Placeholder / consistency check

- Property names consistent: `by_scoreline`, `scoreline`, `settled`, `roi_pct`, `pnl_units`, `avg_odds`
- Sort expectation in test: with settled counts 2, 2, 1 → `1-0`, `2-1`, `3-0` (tie broken by scoreline asc)
