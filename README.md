# DG standalone cloud webapp (Railway + Postgres)

This app scrapes DataGaffer fixture feeds, builds strategy pages (including LM Strat), and tracks bet logs with persistent storage.

Sources:
- [Goal Zone](https://www.datagaffer.com/goal_zone)
- [Outlooks (Win Outlook)](https://www.datagaffer.com/outlooks#win-outlook)
- [Team Data](https://www.datagaffer.com/team_data)
- [Dashboard](https://www.datagaffer.com/dashboard)

## Local setup

```powershell
cd D:\DG
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Run app:

```powershell
& "D:\DG\.venv\Scripts\python.exe" -m uvicorn app.main:app --port 8000
```

Open `http://127.0.0.1:8000`.

## Database behavior

- If `DATABASE_URL` is set (Railway Postgres), the app uses Postgres.
- If `DATABASE_URL` is not set, it falls back to local SQLite: `data/dgauto.db`.
- Stored in DB:
  - latest scraped slate data
  - main bet log
  - LM bet log

## Railway deployment (step-by-step)

1. **Push repo to GitHub**
   - Ensure code is committed and available on GitHub.

2. **Create Railway project**
   - Go to Railway dashboard, click **New Project**.
   - Choose **Deploy from GitHub repo**, select this repo.

3. **Add Postgres service**
   - In the same Railway project, click **New** -> **Database** -> **PostgreSQL**.
   - Railway automatically provides `DATABASE_URL` to services in the project.

4. **Configure app service**
   - Open your app service -> **Variables**.
   - Confirm `DATABASE_URL` is present.
   - Add app vars if needed:
     - `APP_ENV=prod`
     - `DG_LOGIN_URL=https://www.datagaffer.com/login`
     - `DG_GOAL_ZONE_URL=https://www.datagaffer.com/goal_zone`
     - `DG_WIN_OUTLOOK_URL=https://www.datagaffer.com/outlooks#win-outlook`

5. **Set start command**
   - Railway usually detects automatically, but if required set:
   - `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

6. **Deploy**
   - Trigger deploy from Railway.
   - Open the generated public URL.

7. **First-time initialize data**
   - Visit homepage and click **Refresh from DataGaffer**.
   - Open strategy pages and sync bet logs.

## Auto-resolve (API-Football)

Open bets can be settled automatically using [API-Football](https://www.api-football.com/) (same API as the [beginner's guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide)).

1. Register at [dashboard.api-football.com](https://dashboard.api-football.com/register) (free tier: 100 requests/day).
2. Copy your key from **Account → My Access**.
3. Add to `.env`:

```env
API_FOOTBALL_KEY=your_key_here
```

4. On the Bet Log or LM Bet Log page, click **Auto resolve open**, or wait for the daily job.

Supports all scenario markets: over/under totals, team goals, BTTS, moneyline, and win-or-draw.

### Scheduled auto-resolve (04:30 IST)

While the app is running, it automatically resolves open bets on:

- **Main bet log** (scenario + legacy entries share the same `main` log)
- **LM Strat bet log**

Default schedule: **04:30, 10:30, 16:30, 22:30 Asia/Kolkata** so finished fixtures are resolved through the day. Configure in `.env`:

```env
AUTO_RESOLVE_SCHEDULE_ENABLED=true
AUTO_RESOLVE_TIME=04:30
AUTO_RESOLVE_TIMEZONE=Asia/Kolkata
AUTO_RESOLVE_MAX_RUNTIME_SEC=240
API_FOOTBALL_KEY=your_key_here

# Open-bet settlement: Flashscore ninja feed first, API-Football fallback
BET_SETTLE_SOURCE=flashscore,api_football
FLASHSCORE_FSIGN=SW9D1eZo
FLASHSCORE_DAY_OFFSETS=-1,0,1,2
```

See [docs/flashscore.md](docs/flashscore.md) for feed format, field map, and FSIGN rotation notes.

Manual run (both logs): `POST /api/auto-resolve/all`

### Scheduled fixture refresh

Fixtures are pulled from DataGaffer automatically every **6 hours**, always including **09:00 IST** (also 03:00, 15:00, 21:00 IST). Configure in `.env`:

```env
FIXTURE_REFRESH_SCHEDULE_ENABLED=true
FIXTURE_REFRESH_INTERVAL_HOURS=6
FIXTURE_REFRESH_ANCHOR_HOUR=9
FIXTURE_REFRESH_TIMEZONE=Asia/Kolkata
```

Manual pull: `POST /api/refresh` (or use the Home page button).

External cron (e.g. Railway Cron) if the web process is not always on:

```env
CRON_SECRET=some-long-random-string
```

```http
POST /api/cron/auto-resolve
X-Cron-Secret: some-long-random-string
```

```http
POST /api/cron/refresh
X-Cron-Secret: some-long-random-string
```

## API endpoints

- `POST /api/refresh` - refresh latest slate data
- `GET /api/bets/today` - cross-strategy bets for today's slate
- `GET /api/bets/log` - unified settled bet history (`strategy`, `result`, `days`, `page`)
- `POST /api/cron/refresh` - same as refresh (optional `X-Cron-Secret` header)
- `GET /api/data` - latest slate data
- `GET /api/todays-bets` - scenario-filtered bets
- `GET /api/lm-strat` - LM Strat filtered picks
- `GET /api/h2h-strat` - H2H Trends picks (Min 6 meetings, ≥75% hit rate)
- `POST /api/h2h-bet-log/sync` - sync H2H Strat bets (1u each, separate log)
- `POST /api/h2h-bet-log/auto-resolve` - settle open H2H bets
- `GET /prop-model` - Prop Model Engine dashboard (NBA/MLB Phase 1)
- `GET /api/prop-model` - Prop Model Engine JSON (scraper health + stats)
- `GET /api/bot/prematch` - pre-match model feed for trading bots
- `GET /api/polymarket/exact-score?slug=` - football exact-score Yes prices (Gamma + CLOB)
- `GET /api/polymarket/exact-score/prices?slug=` - prices array only
- `GET /api/correct-score-strat` - priced correct-score baskets for the slate
- `POST /api/correct-score-bet-log/sync` - log qualified correct-score baskets
- `POST /api/correct-score-bet-log/auto-resolve` - settle open correct-score legs
- `POST /api/bet-log/sync-recommended` - sync homepage recommended bets
- `POST /api/lm-bet-log/sync` - sync LM Strat bets
- `POST /api/bet-log/auto-resolve` - resolve open main bet log bets
- `POST /api/lm-bet-log/auto-resolve` - resolve open LM bet log bets
- `POST /api/auto-resolve/all` - resolve both logs in one call
- `POST /api/cron/auto-resolve` - same as above (optional `X-Cron-Secret` header)
- `GET /health` - health check

## H2H Strat (DataGaffer Trends)

[`/h2h-strat`](https://www.datagaffer.com/head_2_head) mirrors the Head 2 Head **Trends** filters:
Min **6** historical meetings and **≥75%** hit rate on Goals (O2.5 / O3.5 / BTTS), Corners
(O8.5 / O9.5 / O10.5), SOT (O7.5 / O8.5 / O9.5), and Win/Draw (home / draw / away). Each
qualified market is logged at **1 unit** to `/h2h-bet-log` (`log_type = "h2h"`). Goals and
1X2 settle from final scores; corners/SOT use API-Football statistics when configured.

## Correct Score Strat (Polymarket)

`/correct-score-strat` prices DataGaffer's top projected scorelines on Polymarket's
`…-exact-score` markets and stakes each basket for **equal payouts**, so the basket profits
whenever any one of the bought lines hits.

Buying a scoreline at price `p` (cents per share, settling at $1) returns `stake / p` on a hit.
Splitting a budget `B` in proportion to price makes every payout `B / Σp`, so a single hit nets
`B · (1 − Σp) / Σp` no matter which line landed. That is positive only while the summed ask
prices stay under 100%, which is the qualifying test. Both the top-5 and top-4 baskets are
priced and the higher expected value wins (a fifth line costing more than its model probability
drags the basket down), with ties going to the wider basket. If neither clears the ROI floor the
fixture is skipped.

Baskets are logged leg-by-leg to `/correct-score-bet-log` (`log_type = "cs"`, `bet_type =
"correct_score"`, `team_name` = the bought scoreline). Legs settle from the final score through
the shared auto-resolve pipeline, and the log regroups them into baskets for hit-rate and ROI
analysis. Re-syncing never touches a fixture that already has legs, so live baskets keep the
prices they were sized at.

Tuning (all optional):

| Variable | Default | Purpose |
| --- | --- | --- |
| `CS_BASKET_UNITS` | `1.0` | Total stake per basket |
| `CS_MIN_GUARANTEED_ROI` | `0.05` | Minimum return on stake when a line hits |
| `CS_PRICE_BUFFER` | `0.005` | Slippage padding added to each ask |
| `CS_MAX_LEG_PRICE` | `0.60` | Reject legs priced above this |
| `CS_MIN_ASK_SHARES` | `0` | Minimum depth at the best ask (0 = off) |
| `CS_MAX_HOURS_AHEAD` | `72` | Only price fixtures inside this window |
| `CS_EV_TIE_TOLERANCE` | `0.01` | EV gap under which the wider basket is preferred |
| `CS_REQUIRE_POSITIVE_EV` | `false` | Also require model probability above market |
| `CS_FIXTURE_WORKERS` | `4` | Fixtures priced in parallel |

## Prop Model Engine (separate package)

NBA + MLB player-prop pipeline lives in `prop-model-engine/` (Node.js + Playwright). Phase 1 covers stats scraping and normalization only.

**Storage:** uses the same Railway `DATABASE_URL` Postgres as the main app (`pm_*` tables). SQLite is only a local fallback when `DATABASE_URL` is unset.

```powershell
cd D:\DG\prop-model-engine
copy .env.example .env
# DATABASE_URL is already on Railway; for local scrapes, copy it from the root .env
npm install
npx playwright install chromium
npm run db:init
npm run scrape:nba
npm run scrape:mlb
```

Open the linked page in the DG dashboard: `http://127.0.0.1:8000/prop-model`
