# Correct Score bet log — scoreline leg stats

Date: 2026-09-21  
Status: Approved for implementation pending user review of this spec

## Goal

On the **Correct Score Bet Log** page, show **leg-level performance grouped by scoreline** (e.g. `1-0`, `2-1`) so operators can see which exact scores are winning or bleeding units.

## Decisions (locked)

| Topic | Choice |
|---|---|
| Aggregation | Leg-level by scoreline (`team_name`, e.g. `"2-1"`) |
| Settlement filter | **Settled only** (`won` / `lost` / `push`) for counts, PnL, ROI |
| ROI | `pnl_units / settled_staked_units` for that scoreline |
| Delivery | Extend existing dashboard payload (Approach A) |
| Season | Inherit page/API season filter (same as Basket Performance) |
| Sort | Settled N descending, then scoreline ascending |

## Non-goals (v1)

- Basket-hit-only view (count score only when it won the basket)
- Including open legs in stake / ROI denominator
- CSV export of scoreline stats
- Min-N filter or pagination of the scoreline table
- Changes to basket sync / resolve logic

## Architecture

```
GET /correct-score-bet-log  +  GET /api/correct-score-bet-log
  └─ _correct_score_log_payload()
       └─ dashboard = correct_score_dashboard(entries)
            └─ by_scoreline: scoreline_leg_stats(entries)

templates/cs_bet_log.html
  └─ Scoreline performance table (under Basket Performance)
```

## Backend

**File:** `app/correct_score_strat.py`

1. Add `scoreline_leg_stats(entries: list[dict]) -> list[dict]`:
   - Group by normalized scoreline string from `team_name` (strip; skip empty).
   - Keep only legs with `status in {"won", "lost", "push"}`.
   - Per group compute:
     - `scoreline` (key)
     - `settled` (n)
     - `won`, `lost`, `push`
     - `win_pct` = won / (won + lost) × 100 when decided > 0, else `0.0` or `null` (match existing `compute_bet_stats` convention)
     - `staked_units` = sum of `units` on settled legs
     - `pnl_units` = sum of `pnl_units` (treat missing as 0)
     - `roi_pct` = pnl / staked × 100 when staked > 0, else `0.0`
     - `avg_odds` = mean of present odds on settled legs (same spirit as `_avg_odds`)
   - Sort: `settled` desc, then `scoreline` asc.
   - Omit scorelines with zero settled legs.

2. Extend `correct_score_dashboard()` return value with:
   ```python
   "by_scoreline": scoreline_leg_stats(entries)
   ```

No new routes required; page and API already return `dashboard`.

## Frontend

**File:** `templates/cs_bet_log.html`

- Add a **Scoreline performance** section directly under the Basket Performance card.
- Table columns: **Score | Settled | Won | Lost | Push | Win% | PnL(u) | ROI% | Avg odds**
- Render from `dashboard.by_scoreline` inside the existing `renderStats` / `renderAll` path so sync and auto-resolve refresh the table.
- Empty state: short “No settled scoreline legs yet.” when the list is empty.
- Reuse existing CS / shared table styles; tint PnL/ROI positive/negative if the page already tints unit PnL elsewhere (optional polish, not blocking).

## Testing

- Unit tests in `tests/test_correct_score_strat.py`:
  - Two scorelines with mixed won/lost/push → correct counts, PnL, ROI.
  - Open legs ignored for that scoreline’s settled/ROI.
  - Empty / all-open input → `[]`.

## Implementation order

1. `scoreline_leg_stats` + wire into `correct_score_dashboard`
2. Unit tests
3. UI table in `cs_bet_log.html`

## Risks

- Long tail of rare scorelines → table length; v1 accepts full list sorted by volume.
- Inconsistent `team_name` formatting (`"2-1"` vs `"2 - 1"`) → normalize with strip; do not invent alias maps in v1 unless real data shows variance.
