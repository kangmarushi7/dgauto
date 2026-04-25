from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from app.models import MatchSignal, RefreshResponse
from app.bet_log import bet_log_dashboard, load_bet_log, resolve_bet, sync_recommended_bets
from app.lm_strat import (
    build_lm_strat_picks,
    lm_dashboard,
    load_lm_bet_log,
    resolve_lm_bet,
    sync_lm_bets,
)
from app.scraper import scrape_datagaffer_sync
from app.signals import merge_outlooks
from app.todays_bets import build_todays_bets_scenarios

app = FastAPI(title="DG Bet Automation")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
LATEST_FILE = DATA_DIR / "latest.json"


def read_latest() -> dict:
    if not LATEST_FILE.exists():
        return {"scraped_at": None, "matches": []}
    return json.loads(LATEST_FILE.read_text(encoding="utf-8"))


def write_latest(payload: dict) -> None:
    LATEST_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@app.get("/")
async def dashboard(request: Request):
    data = read_latest()
    return templates.TemplateResponse(request, "index.html", {"data": data})


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/todays-bets")
async def todays_bets(request: Request):
    data = read_latest()
    scenarios = build_todays_bets_scenarios(data.get("matches", []))
    return templates.TemplateResponse(
        request,
        "todays_bets.html",
        {"data": data, "scenarios": scenarios},
    )


@app.get("/bet-log")
async def bet_log_page(request: Request):
    entries = load_bet_log()
    dashboard = bet_log_dashboard(entries)
    return templates.TemplateResponse(
        request,
        "bet_log.html",
        {"entries": entries, "dashboard": dashboard},
    )


@app.get("/lm-strat")
async def lm_strat_page(request: Request):
    data = read_latest()
    picks = build_lm_strat_picks(data.get("matches", []))
    return templates.TemplateResponse(
        request,
        "lm_strat.html",
        {"data": data, "picks": picks},
    )


@app.get("/lm-bet-log")
async def lm_bet_log_page(request: Request):
    entries = load_lm_bet_log()
    dashboard = lm_dashboard(entries)
    return templates.TemplateResponse(
        request,
        "lm_bet_log.html",
        {"entries": entries, "dashboard": dashboard},
    )


@app.post("/api/refresh", response_model=RefreshResponse)
async def refresh():
    try:
        scraped = await run_in_threadpool(scrape_datagaffer_sync)
        merged = merge_outlooks(scraped["win_rows"], scraped["goal_rows"])
        payload = {"scraped_at": scraped["scraped_at"], "matches": merged}
        write_latest(payload)
        return RefreshResponse(
            success=True,
            message="Scrape + analysis completed.",
            scraped_at=scraped["scraped_at"],
            matches=[MatchSignal(**m) for m in merged],
        )
    except Exception as exc:
        detail = str(exc).strip() or repr(exc)
        return RefreshResponse(success=False, message=detail, scraped_at=None, matches=[])


@app.get("/api/data")
async def data():
    return JSONResponse(read_latest())


@app.get("/api/todays-bets")
async def todays_bets_data():
    data = read_latest()
    scenarios = build_todays_bets_scenarios(data.get("matches", []))
    return JSONResponse({"scraped_at": data.get("scraped_at"), "scenarios": scenarios})


@app.get("/api/bet-log")
async def bet_log_data():
    entries = load_bet_log()
    return JSONResponse({"entries": entries, "dashboard": bet_log_dashboard(entries)})


@app.post("/api/bet-log/sync-recommended")
async def bet_log_sync_recommended():
    latest = read_latest()
    result = sync_recommended_bets(latest.get("matches", []))
    entries = load_bet_log()
    return JSONResponse({"result": result, "entries": entries, "dashboard": bet_log_dashboard(entries)})


@app.post("/api/bet-log/{bet_id}/resolve")
async def bet_log_resolve(bet_id: str, payload: dict):
    updated = resolve_bet(bet_id, str(payload.get("result", "")))
    entries = load_bet_log()
    return JSONResponse({"updated": updated, "entries": entries, "dashboard": bet_log_dashboard(entries)})


@app.get("/api/lm-strat")
async def lm_strat_data():
    latest = read_latest()
    picks = build_lm_strat_picks(latest.get("matches", []))
    return JSONResponse({"scraped_at": latest.get("scraped_at"), "picks": picks})


@app.get("/api/lm-bet-log")
async def lm_bet_log_data():
    entries = load_lm_bet_log()
    return JSONResponse({"entries": entries, "dashboard": lm_dashboard(entries)})


@app.post("/api/lm-bet-log/sync")
async def lm_bet_log_sync():
    latest = read_latest()
    picks = build_lm_strat_picks(latest.get("matches", []))
    result = sync_lm_bets(picks)
    entries = load_lm_bet_log()
    return JSONResponse({"result": result, "entries": entries, "dashboard": lm_dashboard(entries)})


@app.post("/api/lm-bet-log/{bet_id}/resolve")
async def lm_bet_log_resolve(bet_id: str, payload: dict):
    updated = resolve_lm_bet(bet_id, str(payload.get("result", "")))
    entries = load_lm_bet_log()
    return JSONResponse({"updated": updated, "entries": entries, "dashboard": lm_dashboard(entries)})
