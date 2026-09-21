# Research page — profitability analytics

Date: 2026-09-21  
Status: Approved for implementation pending user review of this spec

## Goal

Add a **Research** page to the DG dashboard that analyzes settled bets (Main / Arahus / +EV) and surfaces the same multi-angle profitability figures as the offline final report: markets, odds buckets, leagues, rolling windows, and keep/cut playbook.

## Decisions (locked)

| Topic | Choice |
|---|---|
| Compute | On demand via **Refresh analysis**; cache results |
| UI | Strategy tabs: Combined / Main / Arahus / +EV |
| Sections per tab | Summary → markets → odds → leagues → rolling 25/50/100 → keep/cut |
| Exports | Download PDF + Download MD from last successful run |
| Scope v1 | Main, Arahus, +EV only |
| Classifier | Team overs before match overs (fix “Team Over 1.5” ≠ match Over 1.5) |

## Non-goals (v1)

- Netcup DB sync from this page
- LM / NO / H2H / CS / Prop logs in the research slice
- Live recompute on every page load
- Editing or resolving bets from Research

## Architecture

```
Browser /research
  ├─ GET  /api/research          → cached JSON (or empty state)
  ├─ POST /api/research/refresh  → rebuild cache + MD/PDF artifacts
  └─ GET  /api/research/export/{md|pdf}

app/research_analytics.py
  └─ load bets → classify → aggregate → payload + playbook

data/research_analysis.json     (cache)
data/research_report.md
data/research_report.pdf
```

### Backend module

Extract/shared logic from `scripts/build_final_profitability_report.py` into `app/research_analytics.py`:

- Load settled (+ open counts) from `bet_entries` for `main`, `arahus`, `ev`
- Fixed `classify_market` (team overs first; `to15*` / `o15*` bet_type hints)
- Aggregations: overall, by market, by odds bucket, by league (top volume + top ROI), rolling 25/50/100 calendar days (fixture date IST)
- Playbook: keep/cut + cross-strategy durable angles
- `build_research_payload() -> dict`
- `refresh_research_cache() -> dict` writes JSON + MD + PDF

### API

| Method | Path | Behavior |
|---|---|---|
| GET | `/research` | Jinja page; nav_current=`research` |
| GET | `/api/research` | Cached payload; `{ ok, generated_at, status, data }` or empty if never refreshed |
| POST | `/api/research/refresh` | Rebuild synchronously; return payload + timings. If runtime > ~60s proves painful later, upgrade to 202+poll — not required for v1 |
| GET | `/api/research/export/md` | Serve last MD (404 if missing) |
| GET | `/api/research/export/pdf` | Serve last PDF (404 if missing) |

### Frontend

- `templates/research.html` + `static/research.js` (+ small CSS in `static/research.css` or page section in existing style)
- Match existing app chrome (nav, hero, tables) — not a separate design system
- Toolbar: Refresh, status text, generated_at, Download MD, Download PDF
- Tabs switch client-side over cached `data.combined|main|arahus|ev`
- Empty state when no cache: prompt to Refresh
- PnL/ROI cells tinted positive/negative using existing patterns where possible

### Navigation

Add top-level link in `templates/includes/app_nav.html`:

`Research` → `/research` (alongside Home, Today's Bets, Bet Log, Strategy Logic)

## Data / correctness

- Source of truth: live `DATABASE_URL` Postgres `bet_entries`
- +EV stake normalized to 1u for ROI
- Rolling windows use fixture date in IST
- Exclude `missing` odds from “cut” playbook odds rules (same as final report)
- Open bets counted for status only; PnL tables use settled `won|lost|push`

## UX status machine

| Status | Meaning |
|---|---|
| `never_run` | No cache file |
| `ready` | Cache present |
| `running` | Refresh in flight (button disabled) |
| `error` | Last refresh failed; show message; keep prior cache if any |

## Testing

- Unit: classifier regression — `Team Over 1.5 Goals` / `to15_*` → `team_o1.5`; match `over1.5` / `o15_*` → `over_1.5`
- API: refresh writes cache; GET returns it; export endpoints 200 after refresh, 404 before
- Smoke: `/research` renders with nav current

## Implementation order

1. `app/research_analytics.py` (+ thin reuse of PDF helper)
2. Routes in `app/main.py`
3. Template / JS / CSS + nav link
4. Classifier unit test
5. Manual smoke of Refresh + downloads

## Risks

- Refresh can be slow (thousands of bets) — sync OK for v1; show “Running…” clearly
- PDF generation depends on `fpdf2` — already used by report scripts; ensure listed if not in requirements
