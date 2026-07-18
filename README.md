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
```

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
- `POST /api/cron/refresh` - same as refresh (optional `X-Cron-Secret` header)
- `GET /api/data` - latest slate data
- `GET /api/todays-bets` - scenario-filtered bets
- `GET /api/lm-strat` - LM Strat filtered picks
- `POST /api/bet-log/sync-recommended` - sync homepage recommended bets
- `POST /api/lm-bet-log/sync` - sync LM Strat bets
- `POST /api/bet-log/auto-resolve` - resolve open main bet log bets
- `POST /api/lm-bet-log/auto-resolve` - resolve open LM bet log bets
- `POST /api/auto-resolve/all` - resolve both logs in one call
- `POST /api/cron/auto-resolve` - same as above (optional `X-Cron-Secret` header)
- `GET /health` - health check
