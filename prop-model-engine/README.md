# Prop Model Engine

Separate Node.js package for NBA + MLB player-prop stats (Phase 1: scrape → normalize → SQLite).

Later phases (lines, projections, edge engine, calibration) plug into the same DB without changing this layout.

## Setup

```powershell
cd D:\DG\prop-model-engine
copy .env.example .env
# Set DATABASE_URL to the same Postgres URL as the DG app (Railway already has it).
npm install
npx playwright install chromium
npm run db:init
```

With `DATABASE_URL` set, tables are created as `pm_*` on the **shared Postgres**.
Without it, the package falls back to local SQLite at `data/prop-model.db`.

## Manual scrapes

```powershell
npm run scrape:nba
npm run scrape:mlb
npm run normalize
npm run scrape:all
```

Raw JSON lands in `data/raw/{sport}/{YYYY-MM-DD}/`. Normalized rows go to Postgres (`pm_*` tables via `DATABASE_URL`) or local SQLite.

## Daily scheduler

```powershell
npm start
```

Cron times come from `.env` (`NBA_CRON`, `MLB_CRON`).

## Dashboard

The DG FastAPI app exposes this package at **`/prop-model`**. It reads the same `DATABASE_URL` Postgres (`pm_*` tables). On app startup it also ensures those tables exist.

## Phase status

| Phase | Status |
|-------|--------|
| 1 Stats scrapers + normalizer | Implemented |
| 2 Lines scraper | Not started |
| 3 Projection models | Not started |
| 4 Edge engine + API | Schema stubs only |
| 5 Live stakes | Not started |
| 6 Calibration | Not started |
