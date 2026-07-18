from __future__ import annotations

import os

from fastapi import FastAPI, Header, HTTPException, Query, Request
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
from app.fixture_refresh import refresh_fixtures_sync
from app.scheduler import (
    run_all_auto_resolves,
    run_fixture_refresh,
    start_auto_resolve_scheduler,
    stop_auto_resolve_scheduler,
)
from app.db import check_db_health, init_db, load_state, save_state
from app.lm_strat import (
    build_lm_strat_picks,
    lm_dashboard,
    load_lm_bet_log,
    resolve_lm_bet,
    sync_lm_bets,
)
from app.no_strat import (
    build_no_strat_picks,
    load_no_bet_log,
    no_dashboard,
    resolve_no_bet,
    sync_no_bets,
)
from app.plus_ev_strat import (
    build_plus_ev_picks,
    enrich_plus_ev_entries,
    load_plus_ev_bet_log,
    plus_ev_dashboard,
    resolve_plus_ev_bet,
    sync_plus_ev_bets,
)
from app.fixture_detail import get_fixture_detail_from_state
from app.slate import build_fixture_slate
from app.todays_bets import build_todays_bets_scenarios
from app.bot_feed import build_prematch_feed, get_prematch_fixture
from app.seasons import DEFAULT_SEASON_ID, filter_entries_by_season, parse_season, season_context

app = FastAPI(title="DG Bet Automation")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

def read_latest() -> dict:
    return load_state("latest_data", {"scraped_at": None, "matches": []})


def write_latest(payload: dict) -> None:
    save_state("latest_data", payload)


def _refresh_payload() -> dict:
    result = refresh_fixtures_sync()
    latest = read_latest()
    return {
        **result,
        "matches": latest.get("matches") or [],
        "scraped_at": latest.get("scraped_at"),
    }


def _cron_authorized(x_cron_secret: str | None = Header(default=None)) -> None:
    expected = os.getenv("CRON_SECRET", "").strip()
    if not expected:
        return
    if x_cron_secret != expected:
        raise HTTPException(status_code=401, detail="Invalid cron secret")


def _resolve_season(season: int | None = None) -> int:
    return parse_season(season)


def _bet_log_payload(*, legacy: bool = False, season: int | None = None) -> dict:
    season_id = _resolve_season(season)
    entries = load_bet_log()
    scope = "legacy" if legacy else "scenarios"
    scoped = filter_bet_entries(entries, legacy=legacy)
    season_entries = filter_entries_by_season(scoped, season_id)
    legacy_season = filter_entries_by_season(filter_bet_entries(entries, legacy=True), season_id)
    return {
        **season_context(season_id),
        "entries": enrich_bet_entries(season_entries),
        "dashboard": bet_log_dashboard(season_entries, scope=scope),
        "legacy_count": len(legacy_season),
    }


def _strat_log_payload(
    entries: list,
    dashboard_fn,
    *,
    season: int | None = None,
    enrich_fn=None,
) -> dict:
    season_id = _resolve_season(season)
    filtered = filter_entries_by_season(entries, season_id)
    return {
        **season_context(season_id),
        "entries": enrich_fn(filtered) if enrich_fn else filtered,
        "dashboard": dashboard_fn(filtered),
    }


def _bot_api_authorized(x_api_key: str | None = Header(default=None, alias="X-Api-Key")) -> None:
    """Require X-Api-Key when BOT_API_KEY is set in the environment."""
    expected = os.getenv("BOT_API_KEY", "").strip()
    if not expected:
        return
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.on_event("startup")
async def startup_event():
    init_db()
    start_auto_resolve_scheduler()


@app.on_event("shutdown")
async def shutdown_event():
    stop_auto_resolve_scheduler()


def _home_context() -> dict:
    data = read_latest()
    matches = data.get("matches", [])
    slate = build_fixture_slate(matches)
    return {"data": data, "slate": slate, "matches": matches}


@app.get("/")
async def dashboard(request: Request):
    return templates.TemplateResponse(request, "index.html", _home_context())


@app.get("/fixture/{fixture_id}")
async def fixture_page(request: Request, fixture_id: int):
    data = read_latest()
    detail = get_fixture_detail_from_state(data, fixture_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Fixture not found. Refresh from DataGaffer first.")
    return templates.TemplateResponse(
        request,
        "fixture.html",
        {"detail": detail, "data": data},
    )


@app.get("/api/fixture/{fixture_id}")
async def fixture_api(fixture_id: int):
    data = read_latest()
    detail = get_fixture_detail_from_state(data, fixture_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Fixture not found")
    return JSONResponse(detail)


@app.get("/api/slate")
async def slate_data():
    ctx = _home_context()
    return JSONResponse(
        {
            "scraped_at": ctx["data"].get("scraped_at"),
            "slate": ctx["slate"],
            "match_count": len(ctx["matches"]),
        }
    )


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
async def bet_log_page(request: Request, season: int | None = Query(default=None)):
    season_id = _resolve_season(season)
    payload = _bet_log_payload(legacy=False, season=season_id)
    return templates.TemplateResponse(request, "bet_log.html", payload)


@app.get("/lm-strat")
async def lm_strat_page(request: Request):
    data = read_latest()
    picks = build_lm_strat_picks(data.get("matches", []))
    return templates.TemplateResponse(
        request,
        "lm_strat.html",
        {"data": data, "picks": picks},
    )


@app.get("/no-strat")
async def no_strat_page(request: Request):
    data = read_latest()
    picks = build_no_strat_picks(data.get("matches", []))
    return templates.TemplateResponse(
        request,
        "no_strat.html",
        {"data": data, "picks": picks},
    )


@app.get("/no-bet-log")
async def no_bet_log_page(request: Request, season: int | None = Query(default=None)):
    season_id = _resolve_season(season)
    payload = _strat_log_payload(load_no_bet_log(), no_dashboard, season=season_id)
    return templates.TemplateResponse(request, "no_bet_log.html", payload)


@app.get("/plus-ev-strat")
async def plus_ev_strat_page(request: Request):
    data = read_latest()
    picks = build_plus_ev_picks(data)
    return templates.TemplateResponse(
        request,
        "plus_ev_strat.html",
        {"data": data, "picks": picks},
    )


@app.get("/plus-ev-bet-log")
async def plus_ev_bet_log_page(request: Request, season: int | None = Query(default=None)):
    season_id = _resolve_season(season)
    payload = _strat_log_payload(
        load_plus_ev_bet_log(),
        plus_ev_dashboard,
        season=season_id,
        enrich_fn=enrich_plus_ev_entries,
    )
    return templates.TemplateResponse(request, "plus_ev_bet_log.html", payload)


@app.get("/lm-bet-log")
async def lm_bet_log_page(request: Request, season: int | None = Query(default=None)):
    season_id = _resolve_season(season)
    payload = _strat_log_payload(load_lm_bet_log(), lm_dashboard, season=season_id)
    return templates.TemplateResponse(request, "lm_bet_log.html", payload)


@app.post("/api/refresh", response_model=RefreshResponse)
async def refresh():
    try:
        payload = await run_in_threadpool(_refresh_payload)
        return RefreshResponse(
            success=True,
            message="Scrape + analysis completed.",
            scraped_at=payload["scraped_at"],
            matches=[MatchSignal(**m) for m in payload["matches"]],
        )
    except Exception as exc:
        detail = str(exc).strip() or repr(exc)
        return RefreshResponse(success=False, message=detail, scraped_at=None, matches=[])


@app.get("/api/data")
async def data():
    return JSONResponse(read_latest())


@app.get("/api/bot/prematch")
async def bot_prematch_feed(
    slate_only: bool = False,
    plus_ev: bool = True,
    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
):
    """
    Pre-match model feed for external trading bots.
    Set BOT_API_KEY and send header X-Api-Key. In-play data is not included.
    """
    _bot_api_authorized(x_api_key)
    state = read_latest()
    payload = build_prematch_feed(state, slate_only=slate_only, include_plus_ev=plus_ev)
    return JSONResponse(payload)


@app.get("/api/bot/prematch/{fixture_id}")
async def bot_prematch_fixture(
    fixture_id: int,
    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
):
    """Single-fixture pre-match payload."""
    _bot_api_authorized(x_api_key)
    state = read_latest()
    row = get_prematch_fixture(state, fixture_id)
    if not row:
        raise HTTPException(status_code=404, detail="Fixture not found. Refresh from DataGaffer first.")
    return JSONResponse(
        {
            "schema_version": 1,
            "kind": "prematch",
            "scraped_at": state.get("scraped_at"),
            "fixture": row,
        }
    )


@app.get("/api/todays-bets")
async def todays_bets_data():
    data = read_latest()
    scenarios = build_todays_bets_scenarios(data.get("matches", []))
    return JSONResponse({"scraped_at": data.get("scraped_at"), "scenarios": scenarios})


@app.get("/legacy-bet-log")
async def legacy_bet_log_page(request: Request, season: int | None = Query(default=None)):
    season_id = _resolve_season(season)
    payload = _bet_log_payload(legacy=True, season=season_id)
    return templates.TemplateResponse(request, "legacy_bet_log.html", payload)


@app.get("/api/bet-log")
async def bet_log_data(season: int | None = Query(default=None)):
    return JSONResponse(_bet_log_payload(legacy=False, season=season))


@app.get("/api/legacy-bet-log")
async def legacy_bet_log_data(season: int | None = Query(default=None)):
    return JSONResponse(_bet_log_payload(legacy=True, season=season))


@app.post("/api/bet-log/sync-recommended")
async def bet_log_sync_recommended(season: int | None = Query(default=None)):
    payload = await run_in_threadpool(_refresh_payload)
    result = sync_recommended_bets(payload["matches"])
    log_payload = _bet_log_payload(legacy=False, season=season)
    return JSONResponse({"result": result, **log_payload})


@app.post("/api/bet-log/{bet_id}/resolve")
async def bet_log_resolve(bet_id: str, payload: dict, season: int | None = Query(default=None)):
    updated = resolve_bet(bet_id, str(payload.get("result", "")))
    data = _bet_log_payload(legacy=False, season=season)
    return JSONResponse({"updated": updated, **data})


@app.post("/api/legacy-bet-log/{bet_id}/resolve")
async def legacy_bet_log_resolve(bet_id: str, payload: dict, season: int | None = Query(default=None)):
    updated = resolve_bet(bet_id, str(payload.get("result", "")))
    data = _bet_log_payload(legacy=True, season=season)
    return JSONResponse({"updated": updated, **data})


@app.post("/api/bet-log/auto-resolve")
async def bet_log_auto_resolve(season: int | None = Query(default=None)):
    result = await run_in_threadpool(auto_resolve_open_bets, "main")
    data = _bet_log_payload(legacy=False, season=season)
    return JSONResponse({"result": result, **data})


@app.post("/api/legacy-bet-log/auto-resolve")
async def legacy_bet_log_auto_resolve(season: int | None = Query(default=None)):
    result = await run_in_threadpool(auto_resolve_open_bets, "main")
    data = _bet_log_payload(legacy=True, season=season)
    return JSONResponse({"result": result, **data})


@app.post("/api/auto-resolve/all")
async def auto_resolve_all_logs():
    """Resolve open bets on main, LM, NO, and +EV bet logs (same as the daily job)."""
    summary = await run_in_threadpool(run_all_auto_resolves)
    return JSONResponse({"summary": summary})


@app.get("/api/lm-strat")
async def lm_strat_data():
    latest = read_latest()
    picks = build_lm_strat_picks(latest.get("matches", []))
    return JSONResponse({"scraped_at": latest.get("scraped_at"), "picks": picks})


@app.get("/api/no-strat")
async def no_strat_data():
    latest = read_latest()
    picks = build_no_strat_picks(latest.get("matches", []))
    return JSONResponse({"scraped_at": latest.get("scraped_at"), "picks": picks})


@app.get("/api/no-bet-log")
async def no_bet_log_data(season: int | None = Query(default=None)):
    return JSONResponse(_strat_log_payload(load_no_bet_log(), no_dashboard, season=season))


@app.post("/api/no-bet-log/sync")
async def no_bet_log_sync(season: int | None = Query(default=None)):
    latest = read_latest()
    picks = build_no_strat_picks(latest.get("matches", []))
    result = sync_no_bets(picks)
    payload = _strat_log_payload(load_no_bet_log(), no_dashboard, season=season)
    return JSONResponse({"result": result, **payload})


@app.post("/api/no-bet-log/{bet_id}/resolve")
async def no_bet_log_resolve(bet_id: str, payload: dict, season: int | None = Query(default=None)):
    updated = resolve_no_bet(bet_id, str(payload.get("result", "")))
    data = _strat_log_payload(load_no_bet_log(), no_dashboard, season=season)
    return JSONResponse({"updated": updated, **data})


@app.post("/api/no-bet-log/auto-resolve")
async def no_bet_log_auto_resolve(season: int | None = Query(default=None)):
    result = await run_in_threadpool(auto_resolve_open_bets, "no")
    data = _strat_log_payload(load_no_bet_log(), no_dashboard, season=season)
    return JSONResponse({"result": result, **data})


@app.get("/api/plus-ev-strat")
async def plus_ev_strat_data():
    latest = read_latest()
    picks = build_plus_ev_picks(latest)
    return JSONResponse({"scraped_at": latest.get("scraped_at"), "picks": picks})


@app.get("/api/plus-ev-bet-log")
async def plus_ev_bet_log_data(season: int | None = Query(default=None)):
    return JSONResponse(
        _strat_log_payload(
            load_plus_ev_bet_log(),
            plus_ev_dashboard,
            season=season,
            enrich_fn=enrich_plus_ev_entries,
        )
    )


@app.post("/api/plus-ev-bet-log/sync")
async def plus_ev_bet_log_sync(season: int | None = Query(default=None)):
    latest = read_latest()
    picks = build_plus_ev_picks(latest)
    result = sync_plus_ev_bets(picks)
    payload = _strat_log_payload(
        load_plus_ev_bet_log(),
        plus_ev_dashboard,
        season=season,
        enrich_fn=enrich_plus_ev_entries,
    )
    return JSONResponse({"result": result, **payload})


@app.post("/api/plus-ev-bet-log/{bet_id}/resolve")
async def plus_ev_bet_log_resolve(bet_id: str, payload: dict, season: int | None = Query(default=None)):
    updated = resolve_plus_ev_bet(bet_id, str(payload.get("result", "")))
    data = _strat_log_payload(
        load_plus_ev_bet_log(),
        plus_ev_dashboard,
        season=season,
        enrich_fn=enrich_plus_ev_entries,
    )
    return JSONResponse({"updated": updated, **data})


@app.post("/api/plus-ev-bet-log/auto-resolve")
async def plus_ev_bet_log_auto_resolve(season: int | None = Query(default=None)):
    result = await run_in_threadpool(auto_resolve_open_bets, "ev")
    data = _strat_log_payload(
        load_plus_ev_bet_log(),
        plus_ev_dashboard,
        season=season,
        enrich_fn=enrich_plus_ev_entries,
    )
    return JSONResponse({"result": result, **data})


@app.get("/api/lm-bet-log")
async def lm_bet_log_data(season: int | None = Query(default=None)):
    return JSONResponse(_strat_log_payload(load_lm_bet_log(), lm_dashboard, season=season))


@app.post("/api/lm-bet-log/sync")
async def lm_bet_log_sync(season: int | None = Query(default=None)):
    latest = read_latest()
    picks = build_lm_strat_picks(latest.get("matches", []))
    result = sync_lm_bets(picks)
    payload = _strat_log_payload(load_lm_bet_log(), lm_dashboard, season=season)
    return JSONResponse({"result": result, **payload})


@app.post("/api/lm-bet-log/{bet_id}/resolve")
async def lm_bet_log_resolve(bet_id: str, payload: dict, season: int | None = Query(default=None)):
    updated = resolve_lm_bet(bet_id, str(payload.get("result", "")))
    data = _strat_log_payload(load_lm_bet_log(), lm_dashboard, season=season)
    return JSONResponse({"updated": updated, **data})


@app.post("/api/lm-bet-log/auto-resolve")
async def lm_bet_log_auto_resolve(season: int | None = Query(default=None)):
    result = await run_in_threadpool(auto_resolve_open_bets, "lm")
    data = _strat_log_payload(load_lm_bet_log(), lm_dashboard, season=season)
    return JSONResponse({"result": result, **data})


@app.post("/api/cron/auto-resolve")
async def cron_auto_resolve(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """External cron hook (e.g. Railway). Set CRON_SECRET and send header X-Cron-Secret."""
    _cron_authorized(x_cron_secret)
    summary = await run_in_threadpool(run_all_auto_resolves)
    return JSONResponse({"ok": True, "summary": summary})


@app.post("/api/cron/refresh")
async def cron_refresh(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """External hook to pull fixtures (same as POST /api/refresh)."""
    _cron_authorized(x_cron_secret)
    result = await run_in_threadpool(run_fixture_refresh)
    return JSONResponse({"ok": bool(result.get("success")), **result})
