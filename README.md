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

## API endpoints

- `POST /api/refresh` - refresh latest slate data
- `GET /api/data` - latest slate data
- `GET /api/todays-bets` - scenario-filtered bets
- `GET /api/lm-strat` - LM Strat filtered picks
- `POST /api/bet-log/sync-recommended` - sync homepage recommended bets
- `POST /api/lm-bet-log/sync` - sync LM Strat bets
- `GET /health` - health check
