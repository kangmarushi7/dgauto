# xGOT strategy + bet log (paper research)

Date: 2026-10-05  
Status: Implemented (pending deploy)

## Goal

Add a dedicated **xGOT** strategy and bet log that:

1. Logs **all slate fixtures with pre-match projections** (no hot-game pre-filter).
2. Opens paper bets on **Over 2.5, Over 3.5, BTTS Yes, match SOT over, and favorite moneyline**.
3. Stores projection metrics on each row so the bet log can **slice filters after the fact** (top 10%/20%, absolute floors) and recompute win rates / PnL for the active slice.

Motivation: post-match xGOT looked strong for Over 2.5, but pre-match top-decile samples are still too small to lock a filter. Log the universe first; decide noise cuts from settled data.

## Decisions (locked)

| Topic | Choice |
|---|---|
| Approach | New isolated strategy (`log_type=xgot`), not tagging Main |
| Pre-filter at sync | **None** — any fixture with usable projections is eligible |
| Markets | O2.5, O3.5, BTTS Yes, match SOT over, favorite ML |
| Capital | **Paper only** — not LIVE / not Trade Picks v1 |
| Buckets | Optional LOGGING category later; v1 can omit or add `XGOT_research` as LOGGING |
| Date UX | Shared Logs date filter (today default / Show all / date picker) |
| Slice UI | Percentile + optional min thresholds + market filter; stats follow slice |
| Resolve | Reuse `auto_resolve_open_bets("xgot")` + existing score/SOT paths |

## Non-goals (v1)

- LIVE staking or inclusion in Trade Picks capital feed
- Claiming a betting edge or fixed “top 10% only” sync rule
- Match Dynamics page / missing `/match_dynamics.json` feed
- Historical backfill of past seasons (optional follow-up)
- Changing Main / H2H selection logic

## Projection source

Read from latest DG state `fixtures_by_id[fid].sim_stats` (and heat extras when useful):

| Metric | Primary path |
|---|---|
| xGOT | `sim_stats.projected_xg.xgot.{home,away,total}` (may be absent on current DG feed) |
| Big chances | `sim_stats.big_chances_created.*` or heat `projected_stats.{home,away}.big_chances_created` |
| Box shots | `sim_stats.shots_inside_box.{home,away,total}` |
| SOT | `sim_stats.shots_on_target.{home,away,total}` |
| Goals xG / npxG | `sim_stats.xg.*` / `projected_xg.non_penalty_xg.*` |

**Eligible fixture:** has `fixture_id` and at least combined projected **xGOT total** (or fallback: big chances total + box shots total) present and finite.

Promote these onto pick/bet rows as flat fields, e.g.:

- `proj_xgot_home`, `proj_xgot_away`, `proj_xgot_total`
- `proj_big_chances_home/away/total`
- `proj_box_shots_home/away/total`
- `proj_sot_home/away/total`
- `proj_xg_total` (optional)

`bet_entries` needs projection totals for offline slicing after fixtures leave live state.

**v1 storage (locked):** add nullable columns on `bet_entries`:

- `fixture_id` (String, indexed) — if not already present on this table
- `proj_xgot_total`, `proj_big_chances_total`, `proj_box_shots_total`, `proj_sot_total` (Float, nullable)

Home/away breakdowns are optional v1 (can recompute from `fixtures_by_id` on the strat page only). Bet log slices use the four totals above.

## Markets

| UI label | `bet_type` | Selection rule | Odds |
|---|---|---|---|
| Over 2.5 | `xgot_o25` | Always if fixture eligible | `over_2_5_odds` |
| Over 3.5 | `xgot_o35` | Always if eligible | `over_3_5_odds` |
| BTTS Yes | `xgot_btts` | Always if eligible | `btts_yes_odds` |
| SOT Over L | `xgot_sot_o{L}` | Match total SOT over; line = nearest half-line at or below projected SOT total from `{7.5,8.5,9.5,10.5}` (skip if projection missing) | DG/book SOT over if available; else `null` odds, status open/pending |
| Moneyline | `xgot_ml` | Favorite by DG 1X2 odds (lower price among home/away; skip draws-as-favorite) | That side’s odds; `team_name` = selected team |

Units: flat **1.0** paper unit. Skip a market row if required odds key is missing **except** SOT may insert with null odds for research volume (resolve still works when stats arrive).

Resolve kinds (via `bet_scenarios` / dedicated map):

- `xgot_o25` → `over2.5`
- `xgot_o35` → `over3.5`
- `xgot_btts` → `btts`
- `xgot_sot_o*` → `h2h_sot` (reuse SOT total settle)
- `xgot_ml` → `moneyline` (team from `team_name`)

## Sync / pages / API

Mirror LM:

| Piece | Path |
|---|---|
| Module | `app/xgot_strat.py` — `LOG_TYPE="xgot"`, `build_xgot_picks`, `sync_xgot_bets`, dashboard helpers |
| Strat page | `/xgot-strat` + `templates/xgot_strat.html` |
| Bet log | `/xgot-bet-log` + `templates/xgot_bet_log.html` |
| APIs | `/api/xgot-strat`, `/api/xgot-bet-log`, sync, resolve, auto-resolve, export |
| Nav | Strategies + Logs |
| Auto-sync | `app/bet_sync.py` |
| Unified | `app/unified_bets.py` `STRATEGY_META` + `LOG_TYPES` (Today’s Bets optional) |
| Auto-resolve | include `"xgot"` in `run_all_auto_resolves` |

Strat page shows today’s candidate fixtures with projection columns and which markets would sync. Bet log uses shared date filter + **slice panel**.

## Bet log slice panel

Controls (client-side on loaded season entries, or server query — client OK for v1 volume):

1. **Rank by:** `proj_xgot_total` | `proj_big_chances_total` | `proj_box_shots_total`  
2. **Percentile:** All | Top 50% | Top 20% | Top 10% (of distinct fixtures in the current date scope, then keep bets for those fixtures)  
3. **Min threshold (optional):** numeric floor on the rank metric  
4. **Market:** All | O2.5 | O3.5 | BTTS | SOT | ML  

Performance card and table rows follow the slice. Export CSV exports the **current slice** (or full season with a toggle — default current slice).

## Architecture

```
slate / fixtures_by_id
  → build_xgot_picks (all eligible fixtures × markets)
  → sync_xgot_bets → insert_bets("xgot", …)
  → xgot bet log UI (date scope + slice) → win% / PnL
  → auto_resolve_open_bets("xgot")
```

## Testing

- Unit: projection extraction; eligibility; market row generation (O2.5/O3.5/BTTS/ML/SOT line pick); resolve kind mapping.
- Unit: percentile slice keeps correct fixture set (stable ties: higher metric first, then fixture_id).
- Smoke: sync inserts without duplicating on re-sync (existing dedupe key).

## Rollout

1. Ship paper strat + log + sync + resolve.  
2. Run alongside Main for ≥ several hundred settled fixtures.  
3. Use slice panel to compare top 10% xGOT vs big chances vs box shots.  
4. Only then consider LOGGING→TRACKING→LIVE or Trade Picks inclusion.

## Open points resolved in this spec

| Question | Answer |
|---|---|
| Filter at sync vs log-all | **Log-all**; filter in UI |
| Markets | O2.5, O3.5, BTTS, SOT over, favorite ML |
| Capital | Paper only |
| SOT line | Nearest half-line ≤ projected match SOT from fixed ladder |
