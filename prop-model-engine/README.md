# Prop Model Engine

Separate Node.js package for NBA + MLB player-prop stats (Phase 1: scrape → normalize → SQLite).

Later phases (lines, projections, edge engine, calibration) plug into the same DB without changing this layout.

## Setup

```powershell
cd D:\DG\prop-model-engine
copy .env.example .env
npm install
npx playwright install chromium
npm run db:init
```

## Manual scrapes

```powershell
npm run scrape:nba
npm run scrape:mlb
npm run normalize
npm run scrape:all
```

Raw JSON lands in `data/raw/{sport}/{YYYY-MM-DD}/`. Normalized rows go to SQLite (`data/prop-model.db` by default).

## Daily scheduler

```powershell
npm start
```

Cron times come from `.env` (`NBA_CRON`, `MLB_CRON`).

## Dashboard

The DG FastAPI app exposes this package at **`/prop-model`** (scraper health, player counts, recent stats). It reads the same SQLite file via `PROP_MODEL_DB_PATH` (defaults to `prop-model-engine/data/prop-model.db`).

## Phase status

| Phase | Status |
|-------|--------|
| 1 Stats scrapers + normalizer | Implemented |
| 2 Lines scraper | Not started |
| 3 Projection models | Not started |
| 4 Edge engine + API | Schema stubs only |
| 5 Live stakes | Not started |
| 6 Calibration | Not started |
