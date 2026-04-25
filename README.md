# DG standalone cloud webapp (DataGaffer scraper)

This project now provides a standalone webapp that:

1. Logs into DataGaffer using your credentials
2. Scrapes `Goal Zone` and `Win Outlook`
3. Merges fixtures across both sources
4. Calculates simple bet signals (`high`, `medium`, `watch`)
5. Shows everything in a web dashboard

Sources:
- [Goal Zone](https://www.datagaffer.com/goal_zone)
- [Outlooks (Win Outlook)](https://www.datagaffer.com/outlooks#win-outlook)

## Local setup

```powershell
cd D:\DG
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

Create env file:

```powershell
copy .env.example .env
```

Set your credentials and (if needed) CSS selectors in `.env`:

- `DG_EMAIL`
- `DG_PASSWORD`
- `DG_LOGIN_URL`
- `DG_EMAIL_SELECTOR`
- `DG_PASSWORD_SELECTOR`
- `DG_SUBMIT_SELECTOR`

Run app:

```powershell
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`, then click **Refresh from DataGaffer**.

## Deploy to cloud (Render)

1. Push this repository to GitHub.
2. Create a new Render Web Service using this repo.
3. Render will use `Dockerfile` + `render.yaml`.
4. Add environment variables in Render dashboard:
   - `DG_EMAIL`
   - `DG_PASSWORD`
   - `DG_LOGIN_URL` (if different)
   - `DG_EMAIL_SELECTOR`
   - `DG_PASSWORD_SELECTOR`
   - `DG_SUBMIT_SELECTOR`
5. Deploy and open the app URL.

## API endpoints

- `POST /api/refresh` - Run login + scrape + signal generation
- `GET /api/data` - Return latest scraped dataset
- `GET /health` - Health check

## Notes

- The scraper is selector-configurable because login forms can change.
- Never hardcode credentials in code; keep them in env vars only.
- The first refresh after deployment may be slightly slower due to browser startup.
