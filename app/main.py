from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from app.models import MatchSignal, RefreshResponse
from app.bet_log import (
    bet_log_dashboard,
    enrich_bet_entries,
    filter_bet_entries,
    load_bet_log,
    resolve_bet,
    sync_recommended_bets,
)
from app.auto_resolve import auto_resolve_open_bets
from app.db import check_db_health, init_db, load_state, save_state
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

def read_latest() -> dict:
    return load_state("latest_data", {"scraped_at": None, "matches": []})


def write_latest(payload: dict) -> None:
    save_state("latest_data", payload)


@app.on_event("startup")
async def startup_event():
    init_db()


@app.get("/")
async def dashboard(request: Request):
    data = read_latest()
    return templates.TemplateResponse(request, "index.html", {"data": data})


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/health/db")
async def health_db():
    status = check_db_health()
    return status


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
    scenario_entries = filter_bet_entries(entries, legacy=False)
    legacy_count = len(filter_bet_entries(entries, legacy=True))
    return templates.TemplateResponse(
        request,
        "bet_log.html",
        {
            "entries": enrich_bet_entries(scenario_entries),
            "dashboard": bet_log_dashboard(entries, scope="scenarios"),
            "legacy_count": legacy_count,
        },
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


def _bet_log_payload(*, legacy: bool = False) -> dict:
    entries = load_bet_log()
    scope = "legacy" if legacy else "scenarios"
    filtered = filter_bet_entries(entries, legacy=legacy) if legacy else filter_bet_entries(entries, legacy=False)
    return {
        "entries": enrich_bet_entries(filtered),
        "dashboard": bet_log_dashboard(entries, scope=scope),
        "legacy_count": len(filter_bet_entries(entries, legacy=True)),
    }


@app.get("/legacy-bet-log")
async def legacy_bet_log_page(request: Request):
    entries = load_bet_log()
    legacy_entries = filter_bet_entries(entries, legacy=True)
    return templates.TemplateResponse(
        request,
        "legacy_bet_log.html",
        {
            "entries": enrich_bet_entries(legacy_entries),
            "dashboard": bet_log_dashboard(entries, scope="legacy"),
        },
    )


@app.get("/api/bet-log")
async def bet_log_data():
    return JSONResponse(_bet_log_payload(legacy=False))


@app.get("/api/legacy-bet-log")
async def legacy_bet_log_data():
    return JSONResponse(_bet_log_payload(legacy=True))


@app.post("/api/bet-log/sync-recommended")
async def bet_log_sync_recommended():
    latest = read_latest()
    result = sync_recommended_bets(latest.get("matches", []))
    payload = _bet_log_payload(legacy=False)
    return JSONResponse({"result": result, **payload})


@app.post("/api/bet-log/{bet_id}/resolve")
async def bet_log_resolve(bet_id: str, payload: dict):
    updated = resolve_bet(bet_id, str(payload.get("result", "")))
    data = _bet_log_payload(legacy=False)
    return JSONResponse({"updated": updated, **data})


@app.post("/api/legacy-bet-log/{bet_id}/resolve")
async def legacy_bet_log_resolve(bet_id: str, payload: dict):
    updated = resolve_bet(bet_id, str(payload.get("result", "")))
    data = _bet_log_payload(legacy=True)
    return JSONResponse({"updated": updated, **data})


@app.post("/api/bet-log/auto-resolve")
async def bet_log_auto_resolve():
    result = await run_in_threadpool(auto_resolve_open_bets, "main")
    data = _bet_log_payload(legacy=False)
    return JSONResponse({"result": result, **data})


@app.post("/api/legacy-bet-log/auto-resolve")
async def legacy_bet_log_auto_resolve():
    result = await run_in_threadpool(auto_resolve_open_bets, "main")
    data = _bet_log_payload(legacy=True)
    return JSONResponse({"result": result, **data})


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


@app.post("/api/lm-bet-log/auto-resolve")
async def lm_bet_log_auto_resolve():
    result = await run_in_threadpool(auto_resolve_open_bets, "lm")
    entries = load_lm_bet_log()
    return JSONResponse({"result": result, "entries": entries, "dashboard": lm_dashboard(entries)})
