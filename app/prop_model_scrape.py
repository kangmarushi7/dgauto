"""Python Playwright scrapers for Prop Model Engine (dashboard Run button).

Writes directly to pm_* tables on the shared app DB — no npm required in prod.
"""

from __future__ import annotations

import re
import time
import traceback
from typing import Any

from app.prop_model import (
    insert_scrape_log,
    insert_stat_raw,
    set_scrape_job,
    upsert_player,
    utc_now_iso,
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _slug(name: str, team: str = "") -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    team_part = re.sub(r"[^a-z0-9]+", "-", (team or "").lower()).strip("-")
    return f"{base}:{team_part}" if team_part else base


def _num(text: str | None) -> float | None:
    if text is None:
        return None
    cleaned = str(text).replace(",", "").replace("%", "").strip()
    if not cleaned or cleaned in {"", "-"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _uncomment_tables(page) -> None:
    page.evaluate(
        """() => {
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_COMMENT);
      let node;
      while ((node = walker.nextNode())) {
        const wrap = document.createElement('div');
        wrap.innerHTML = node.nodeValue || '';
        node.parentNode && node.parentNode.insertBefore(wrap, node);
      }
    }"""
    )


def _delay(lo: float = 1.5, hi: float = 3.0) -> None:
    import random

    time.sleep(lo + random.random() * (hi - lo))


def _browser_page(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1440, "height": 900},
        locale="en-US",
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    page = context.new_page()
    return browser, context, page


def scrape_nba(*, season_year: int | None = None, player_limit: int = 25) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    year = season_year or int(__import__("os").getenv("NBA_SEASON_YEAR", "2026"))
    scraped_at = utc_now_iso()
    succeeded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    players_upserted = 0

    with sync_playwright() as p:
        browser, context, page = _browser_page(p)
        try:
            # --- Per-36 ---
            try:
                url = f"https://www.basketball-reference.com/leagues/NBA_{year}_per_minute.html"
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                _delay()
                _uncomment_tables(page)
                rows = page.evaluate(
                    """() => {
                  const table = document.querySelector('#per_minute_stats')
                    || document.querySelector('table.stats_table');
                  if (!table) return [];
                  return Array.from(table.querySelectorAll('tbody tr'))
                    .filter(tr => !tr.classList.contains('thead'))
                    .map(tr => {
                      const a = tr.querySelector('[data-stat="player"] a');
                      if (!a) return null;
                      const get = (s) => tr.querySelector(`[data-stat="${s}"]`)?.textContent?.trim() || null;
                      return {
                        name: a.textContent.trim(),
                        href: a.getAttribute('href') || '',
                        team: get('team_id') || get('team'),
                        position: get('pos'),
                        pts: get('pts'), reb: get('trb'), ast: get('ast'), fg3: get('fg3'), mp: get('mp'), g: get('g')
                      };
                    }).filter(Boolean);
                }"""
                )
                for r in rows:
                    name = r["name"]
                    team = r.get("team")
                    pid = f"nba:{_slug(name, team or '')}"
                    upsert_player(pid, name, team, "nba", r.get("position"))
                    players_upserted += 1
                    for stat_type, key in (
                        ("pts_per36", "pts"),
                        ("reb_per36", "reb"),
                        ("ast_per36", "ast"),
                        ("fg3_per36", "fg3"),
                        ("mp", "mp"),
                        ("games", "g"),
                    ):
                        val = _num(r.get(key))
                        if val is None:
                            continue
                        insert_stat_raw(
                            pid,
                            "nba-per36",
                            {
                                "player_id": pid,
                                "player_name": name,
                                "team": team,
                                "sport": "nba",
                                "stat_type": stat_type,
                                "value": val,
                                "source": "nba-per36",
                                "scraped_at": scraped_at,
                            },
                            scraped_at,
                        )
                insert_scrape_log("nba-per36", "success" if rows else "partial", detail={"count": len(rows)})
                succeeded.append({"source": "nba-per36", "count": len(rows)})
            except Exception as exc:
                msg = str(exc)
                failed.append({"source": "nba-per36", "error": msg})
                insert_scrape_log("nba-per36", "failure", error_message=msg)

            # --- Team pace ---
            try:
                _delay()
                url = f"https://www.basketball-reference.com/leagues/NBA_{year}.html"
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                _uncomment_tables(page)
                teams = page.evaluate(
                    """() => {
                  const table = document.querySelector('#advanced-team')
                    || document.querySelector('table.stats_table');
                  if (!table) return [];
                  return Array.from(table.querySelectorAll('tbody tr'))
                    .filter(tr => !tr.classList.contains('thead'))
                    .map(tr => {
                      const team = tr.querySelector('[data-stat="team"] a, [data-stat="team_name"] a, td[data-stat="team"]')
                        ?.textContent?.trim();
                      const pace = tr.querySelector('[data-stat="pace"]')?.textContent?.trim();
                      return team ? { team, pace } : null;
                    }).filter(Boolean);
                }"""
                )
                for t in teams:
                    insert_stat_raw(
                        None,
                        "nba-team-pace",
                        {
                            "team": t["team"],
                            "sport": "nba",
                            "stat_type": "team_pace",
                            "value": _num(t.get("pace")),
                            "source": "nba-team-pace",
                            "scraped_at": scraped_at,
                        },
                        scraped_at,
                    )
                insert_scrape_log("nba-team-pace", "success" if teams else "partial", detail={"count": len(teams)})
                succeeded.append({"source": "nba-team-pace", "count": len(teams)})
            except Exception as exc:
                msg = str(exc)
                failed.append({"source": "nba-team-pace", "error": msg})
                insert_scrape_log("nba-team-pace", "failure", error_message=msg)

            # --- Injuries ---
            try:
                _delay()
                page.goto(
                    "https://www.rotowire.com/basketball/injury-report.php",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                injuries = page.evaluate(
                    """() => {
                  return Array.from(document.querySelectorAll('table tbody tr'))
                    .map(tr => {
                      const cells = Array.from(tr.querySelectorAll('td')).map(td => td.textContent.trim());
                      if (cells.length < 2) return null;
                      const player = tr.querySelector('a')?.textContent?.trim() || cells[2] || null;
                      return player ? { team: cells[0], position: cells[1], player, status: cells[4] || cells[cells.length-1], raw: cells } : null;
                    }).filter(Boolean);
                }"""
                )
                for inj in injuries[:200]:
                    name = inj["player"]
                    team = inj.get("team")
                    pid = f"nba:{_slug(name, team or '')}"
                    upsert_player(pid, name, team, "nba", inj.get("position"))
                    players_upserted += 1
                    insert_stat_raw(
                        pid,
                        "nba-injuries",
                        {
                            "player_id": pid,
                            "player_name": name,
                            "team": team,
                            "sport": "nba",
                            "stat_type": "injury_status",
                            "value": None,
                            "source": "nba-injuries",
                            "scraped_at": scraped_at,
                            "extra": inj,
                        },
                        scraped_at,
                    )
                insert_scrape_log(
                    "nba-injuries", "success" if injuries else "partial", detail={"count": len(injuries)}
                )
                succeeded.append({"source": "nba-injuries", "count": len(injuries)})
            except Exception as exc:
                msg = str(exc)
                failed.append({"source": "nba-injuries", "error": msg})
                insert_scrape_log("nba-injuries", "failure", error_message=msg)

        finally:
            context.close()
            browser.close()

    return {
        "sport": "nba",
        "succeeded": succeeded,
        "failed": failed,
        "players_upserted": players_upserted,
        "scraped_at": scraped_at,
    }


def scrape_mlb(*, season_year: int | None = None) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    year = season_year or int(__import__("os").getenv("MLB_SEASON_YEAR", "2025"))
    scraped_at = utc_now_iso()
    succeeded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    players_upserted = 0

    with sync_playwright() as p:
        browser, context, page = _browser_page(p)
        try:
            # Batters
            try:
                url = f"https://www.baseball-reference.com/leagues/majors/{year}-standard-batting.html"
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                _delay()
                _uncomment_tables(page)
                batters = page.evaluate(
                    """() => {
                  const table = document.querySelector('#players_standard_batting')
                    || document.querySelector('table.stats_table');
                  if (!table) return [];
                  return Array.from(table.querySelectorAll('tbody tr'))
                    .filter(tr => !tr.classList.contains('thead'))
                    .map(tr => {
                      const a = tr.querySelector('[data-stat="player"] a');
                      if (!a) return null;
                      const get = (s) => tr.querySelector(`[data-stat="${s}"]`)?.textContent?.trim() || null;
                      return {
                        name: a.textContent.trim(),
                        team: get('team_ID') || get('team_id') || get('team'),
                        avg: get('batting_avg'), slg: get('slugging_perc'), ops: get('onbase_plus_slugging'),
                        pa: get('PA'), hr: get('HR'), so: get('SO')
                      };
                    }).filter(Boolean);
                }"""
                )
                for r in batters:
                    name = r["name"]
                    team = r.get("team")
                    pid = f"mlb:{_slug(name, team or '')}"
                    upsert_player(pid, name, team, "mlb", None)
                    players_upserted += 1
                    for stat_type, key in (("avg", "avg"), ("slg", "slg"), ("ops", "ops"), ("pa", "pa"), ("hr", "hr"), ("so", "so")):
                        val = _num(r.get(key))
                        if val is None:
                            continue
                        insert_stat_raw(
                            pid,
                            "mlb-batters",
                            {
                                "player_id": pid,
                                "player_name": name,
                                "team": team,
                                "sport": "mlb",
                                "stat_type": stat_type,
                                "value": val,
                                "source": "mlb-batters",
                                "scraped_at": scraped_at,
                            },
                            scraped_at,
                        )
                insert_scrape_log("mlb-batters", "success" if batters else "partial", detail={"count": len(batters)})
                succeeded.append({"source": "mlb-batters", "count": len(batters)})
            except Exception as exc:
                msg = str(exc)
                failed.append({"source": "mlb-batters", "error": msg})
                insert_scrape_log("mlb-batters", "failure", error_message=msg)

            # Pitchers
            try:
                _delay()
                url = f"https://www.baseball-reference.com/leagues/majors/{year}-standard-pitching.html"
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                _uncomment_tables(page)
                pitchers = page.evaluate(
                    """() => {
                  const table = document.querySelector('#players_standard_pitching')
                    || document.querySelector('table.stats_table');
                  if (!table) return [];
                  return Array.from(table.querySelectorAll('tbody tr'))
                    .filter(tr => !tr.classList.contains('thead'))
                    .map(tr => {
                      const a = tr.querySelector('[data-stat="player"] a');
                      if (!a) return null;
                      const get = (s) => tr.querySelector(`[data-stat="${s}"]`)?.textContent?.trim() || null;
                      return {
                        name: a.textContent.trim(),
                        team: get('team_ID') || get('team_id') || get('team'),
                        ip: get('IP'), so9: get('strikeouts_per_nine') || get('SO9'), era: get('earned_run_avg'), gs: get('GS')
                      };
                    }).filter(Boolean);
                }"""
                )
                for r in pitchers:
                    name = r["name"]
                    team = r.get("team")
                    pid = f"mlb:{_slug(name, team or '')}"
                    upsert_player(pid, name, team, "mlb", "P")
                    players_upserted += 1
                    for stat_type, key in (("ip", "ip"), ("k9", "so9"), ("era", "era"), ("gs", "gs")):
                        val = _num(r.get(key))
                        if val is None:
                            continue
                        insert_stat_raw(
                            pid,
                            "mlb-pitchers",
                            {
                                "player_id": pid,
                                "player_name": name,
                                "team": team,
                                "sport": "mlb",
                                "stat_type": stat_type,
                                "value": val,
                                "source": "mlb-pitchers",
                                "scraped_at": scraped_at,
                            },
                            scraped_at,
                        )
                insert_scrape_log("mlb-pitchers", "success" if pitchers else "partial", detail={"count": len(pitchers)})
                succeeded.append({"source": "mlb-pitchers", "count": len(pitchers)})
            except Exception as exc:
                msg = str(exc)
                failed.append({"source": "mlb-pitchers", "error": msg})
                insert_scrape_log("mlb-pitchers", "failure", error_message=msg)

            # Park factors
            try:
                _delay()
                url = f"https://www.baseball-reference.com/leagues/majors/{year}-factor-pitching.shtml"
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                _uncomment_tables(page)
                parks = page.evaluate(
                    """() => {
                  const table = document.querySelector('table.stats_table') || document.querySelector('table');
                  if (!table) return [];
                  return Array.from(table.querySelectorAll('tbody tr'))
                    .filter(tr => !tr.classList.contains('thead'))
                    .map(tr => {
                      const cells = Array.from(tr.querySelectorAll('th, td')).map(c => c.textContent.trim());
                      const team = tr.querySelector('a')?.textContent?.trim() || cells[0];
                      return team ? { team, batting_factor: cells[1] || null, raw: cells } : null;
                    }).filter(Boolean);
                }"""
                )
                for pf in parks:
                    insert_stat_raw(
                        None,
                        "mlb-park-factors",
                        {
                            "team": pf["team"],
                            "sport": "mlb",
                            "stat_type": "park_factor",
                            "value": _num(pf.get("batting_factor")),
                            "source": "mlb-park-factors",
                            "scraped_at": scraped_at,
                            "extra": pf,
                        },
                        scraped_at,
                    )
                insert_scrape_log(
                    "mlb-park-factors", "success" if parks else "partial", detail={"count": len(parks)}
                )
                succeeded.append({"source": "mlb-park-factors", "count": len(parks)})
            except Exception as exc:
                msg = str(exc)
                failed.append({"source": "mlb-park-factors", "error": msg})
                insert_scrape_log("mlb-park-factors", "failure", error_message=msg)

        finally:
            context.close()
            browser.close()

    return {
        "sport": "mlb",
        "succeeded": succeeded,
        "failed": failed,
        "players_upserted": players_upserted,
        "scraped_at": scraped_at,
    }


def run_scrape_job(sport: str) -> dict[str, Any]:
    sport = (sport or "all").lower().strip()
    if sport not in {"nba", "mlb", "all"}:
        raise ValueError("sport must be nba, mlb, or all")

    results = []
    if sport in {"nba", "all"}:
        results.append(scrape_nba())
    if sport in {"mlb", "all"}:
        results.append(scrape_mlb())

    return {
        "sport": sport,
        "results": results,
        "finished_at": utc_now_iso(),
    }


def start_scrape_background(sport: str) -> dict[str, Any]:
    """Start scrape in a daemon thread. Returns immediately if already running."""
    from app.prop_model import get_scrape_job_status

    status = get_scrape_job_status()
    if status.get("running"):
        return {"started": False, "reason": "already_running", "job": status}

    set_scrape_job(
        running=True,
        sport=sport,
        started_at=utc_now_iso(),
        finished_at=None,
        result=None,
        error=None,
    )

    def _worker() -> None:
        try:
            result = run_scrape_job(sport)
            set_scrape_job(running=False, finished_at=utc_now_iso(), result=result, error=None)
        except Exception as exc:
            set_scrape_job(
                running=False,
                finished_at=utc_now_iso(),
                result=None,
                error=f"{exc}\n{traceback.format_exc()}",
            )
            try:
                insert_scrape_log("prop-model-run", "failure", error_message=str(exc))
            except Exception:
                pass

    import threading

    threading.Thread(target=_worker, daemon=True, name=f"prop-scrape-{sport}").start()
    return {"started": True, "job": get_scrape_job_status()}
