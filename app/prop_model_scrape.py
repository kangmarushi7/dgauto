"""Python Playwright scrapers for Prop Model Engine (dashboard Run button).

Writes directly to pm_* tables on the shared app DB — no npm required in prod.

Notes:
- Baseball-Reference / FanGraphs are Cloudflare-blocked in headless browsers → empty
  pages show up as PARTIAL with 0 rows. MLB uses ESPN leaderboards instead.
- Basketball-Reference usually works; we wait for the real stats table.
"""

from __future__ import annotations

import os
import random
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

ESPN_BATTERS = "https://www.espn.com/mlb/stats/player/_/table/batting/sort/avg/dir/desc"
ESPN_PITCHERS = (
    "https://www.espn.com/mlb/stats/player/_/view/pitching/table/pitching/sort/ERA/dir/asc"
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


def _delay(lo: float = 1.2, hi: float = 2.4) -> None:
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


def _page_block_reason(page) -> str | None:
    """Detect Cloudflare / empty challenge pages."""
    try:
        info = page.evaluate(
            """() => ({
              title: document.title || '',
              text: (document.body && document.body.innerText || '').slice(0, 400)
            })"""
        )
    except Exception:
        return "page evaluate failed"
    title = (info.get("title") or "").lower()
    text = (info.get("text") or "").lower()
    if "just a moment" in title or "security verification" in text or "verify you are not a bot" in text:
        return f"Blocked by site protection ({info.get('title') or 'challenge page'})"
    return None


def _uncomment_tables(page) -> None:
    page.evaluate(
        """() => {
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_COMMENT);
      const nodes = [];
      let node;
      while ((node = walker.nextNode())) nodes.push(node);
      for (const c of nodes) {
        const html = c.nodeValue || '';
        if (!html.includes('<table')) continue;
        const wrap = document.createElement('div');
        wrap.innerHTML = html;
        c.parentNode && c.parentNode.insertBefore(wrap, c);
      }
    }"""
    )


def _goto(page, url: str, *, wait_selector: str | None = None, timeout: int = 60000) -> str | None:
    page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    _delay()
    blocked = _page_block_reason(page)
    if blocked:
        return blocked
    if wait_selector:
        try:
            page.wait_for_selector(wait_selector, timeout=20000)
        except Exception:
            blocked = _page_block_reason(page)
            return blocked or f"Timed out waiting for {wait_selector}"
    return None


def _parse_espn_split(page) -> list[dict[str, Any]]:
    """ESPN stats pages use a left name table + right stats table."""
    return page.evaluate(
        """() => {
      const tables = Array.from(document.querySelectorAll('table'));
      if (tables.length < 2) return [];
      const nameTable = tables[0];
      const statsTable = tables[1];
      const headers = Array.from(statsTable.querySelectorAll('thead th')).map(h => h.textContent.trim());
      const nameRows = Array.from(nameTable.querySelectorAll('tbody tr'));
      const statRows = Array.from(statsTable.querySelectorAll('tbody tr'));
      const n = Math.min(nameRows.length, statRows.length);
      const out = [];
      for (let i = 0; i < n; i++) {
        const nr = nameRows[i];
        const sr = statRows[i];
        const name = nr.querySelector('a')?.textContent?.trim();
        if (!name) continue;
        const spans = Array.from(nr.querySelectorAll('span')).map(s => s.textContent.trim());
        const team = spans.find(s => /^[A-Z]{2,3}$/.test(s)) || null;
        const cells = Array.from(sr.querySelectorAll('td')).map(td => td.textContent.trim());
        const stats = {};
        headers.forEach((h, idx) => { stats[h] = cells[idx] ?? null; });
        out.push({ name, team, position: stats.POS || null, stats });
      }
      return out;
    }"""
    )


def scrape_nba(*, season_year: int | None = None, player_limit: int = 25) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    year = season_year or int(os.getenv("NBA_SEASON_YEAR", "2026"))
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
                err = _goto(page, url, wait_selector="#per_minute_stats tbody tr, table.stats_table tbody tr")
                if err:
                    raise RuntimeError(err)
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
                        team: get('team_id') || get('team'),
                        position: get('pos'),
                        pts: get('pts'), reb: get('trb'), ast: get('ast'), fg3: get('fg3'),
                        mp: get('mp'), g: get('g')
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
                status = "success" if rows else "partial"
                msg = None if rows else "0 players parsed from Basketball-Reference per-36 table"
                insert_scrape_log(
                    "nba-per36",
                    status,
                    error_message=msg,
                    detail={"count": len(rows), "url": url},
                )
                succeeded.append({"source": "nba-per36", "count": len(rows)})
            except Exception as exc:
                msg = str(exc)
                failed.append({"source": "nba-per36", "error": msg})
                insert_scrape_log("nba-per36", "failure", error_message=msg)

            # --- Team pace ---
            try:
                _delay()
                url = f"https://www.basketball-reference.com/leagues/NBA_{year}.html"
                err = _goto(page, url)
                if err:
                    raise RuntimeError(err)
                _uncomment_tables(page)
                teams = page.evaluate(
                    """() => {
                  const table = document.querySelector('#advanced-team')
                    || document.querySelector('table.stats_table');
                  if (!table) return [];
                  return Array.from(table.querySelectorAll('tbody tr'))
                    .filter(tr => !tr.classList.contains('thead'))
                    .map(tr => {
                      const team = tr.querySelector(
                        '[data-stat="team"] a, [data-stat="team_name"] a, td[data-stat="team"]'
                      )?.textContent?.trim();
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
                status = "success" if teams else "partial"
                insert_scrape_log(
                    "nba-team-pace",
                    status,
                    error_message=None if teams else "0 teams parsed",
                    detail={"count": len(teams)},
                )
                succeeded.append({"source": "nba-team-pace", "count": len(teams)})
            except Exception as exc:
                msg = str(exc)
                failed.append({"source": "nba-team-pace", "error": msg})
                insert_scrape_log("nba-team-pace", "failure", error_message=msg)

            # --- Injuries (Rotowire) ---
            try:
                _delay()
                err = _goto(
                    page,
                    "https://www.rotowire.com/basketball/injury-report.php",
                    wait_selector="table tbody tr",
                )
                if err:
                    raise RuntimeError(err)
                injuries = page.evaluate(
                    """() => Array.from(document.querySelectorAll('table tbody tr')).map(tr => {
                      const cells = Array.from(tr.querySelectorAll('td')).map(td => td.textContent.trim());
                      if (cells.length < 2) return null;
                      const player = tr.querySelector('a')?.textContent?.trim() || cells[2] || null;
                      return player ? {
                        team: cells[0], position: cells[1], player,
                        status: cells[4] || cells[cells.length - 1], raw: cells
                      } : null;
                    }).filter(Boolean)"""
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
                status = "success" if injuries else "partial"
                insert_scrape_log(
                    "nba-injuries",
                    status,
                    error_message=None if injuries else "0 injuries parsed",
                    detail={"count": len(injuries)},
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
    """MLB via ESPN leaderboards (Baseball-Reference is Cloudflare-blocked)."""
    from playwright.sync_api import sync_playwright

    scraped_at = utc_now_iso()
    succeeded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    players_upserted = 0

    with sync_playwright() as p:
        browser, context, page = _browser_page(p)
        try:
            # Batters
            try:
                err = _goto(page, ESPN_BATTERS, wait_selector="table tbody tr")
                if err:
                    raise RuntimeError(err)
                batters = _parse_espn_split(page)
                for r in batters:
                    name = r["name"]
                    team = r.get("team")
                    stats = r.get("stats") or {}
                    pid = f"mlb:{_slug(name, team or '')}"
                    upsert_player(pid, name, team, "mlb", r.get("position"))
                    players_upserted += 1
                    mapped = {
                        "avg": stats.get("AVG"),
                        "obp": stats.get("OBP"),
                        "slg": stats.get("SLG"),
                        "ops": stats.get("OPS"),
                        "hr": stats.get("HR"),
                        "so": stats.get("K"),
                        "hits": stats.get("H"),
                        "ab": stats.get("AB"),
                        "tb": stats.get("TB"),
                        "sb": stats.get("SB"),
                    }
                    for stat_type, raw in mapped.items():
                        val = _num(raw)
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
                status = "success" if batters else "partial"
                insert_scrape_log(
                    "mlb-batters",
                    status,
                    error_message=None if batters else "0 batters parsed from ESPN",
                    detail={"count": len(batters), "source_site": "espn"},
                )
                succeeded.append({"source": "mlb-batters", "count": len(batters)})
            except Exception as exc:
                msg = str(exc)
                failed.append({"source": "mlb-batters", "error": msg})
                insert_scrape_log("mlb-batters", "failure", error_message=msg)

            # Pitchers
            try:
                _delay()
                err = _goto(page, ESPN_PITCHERS, wait_selector="table tbody tr")
                if err:
                    raise RuntimeError(err)
                pitchers = _parse_espn_split(page)
                for r in pitchers:
                    name = r["name"]
                    team = r.get("team")
                    stats = r.get("stats") or {}
                    pid = f"mlb:{_slug(name, team or '')}"
                    upsert_player(pid, name, team, "mlb", "P")
                    players_upserted += 1
                    mapped = {
                        "era": stats.get("ERA"),
                        "ip": stats.get("IP"),
                        "k9": stats.get("K/9"),
                        "so": stats.get("K"),
                        "whip": stats.get("WHIP"),
                        "gs": stats.get("GS"),
                        "w": stats.get("W"),
                        "l": stats.get("L"),
                    }
                    for stat_type, raw in mapped.items():
                        val = _num(raw)
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
                status = "success" if pitchers else "partial"
                insert_scrape_log(
                    "mlb-pitchers",
                    status,
                    error_message=None if pitchers else "0 pitchers parsed from ESPN",
                    detail={"count": len(pitchers), "source_site": "espn"},
                )
                succeeded.append({"source": "mlb-pitchers", "count": len(pitchers)})
            except Exception as exc:
                msg = str(exc)
                failed.append({"source": "mlb-pitchers", "error": msg})
                insert_scrape_log("mlb-pitchers", "failure", error_message=msg)

            # Park factors — Baseball-Reference is blocked; log skip clearly
            insert_scrape_log(
                "mlb-park-factors",
                "partial",
                error_message=(
                    "Skipped: Baseball-Reference is Cloudflare-blocked in headless browsers. "
                    "Batters/pitchers now come from ESPN."
                ),
                detail={"count": 0, "skipped": True},
            )
            succeeded.append({"source": "mlb-park-factors", "count": 0, "skipped": True})

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
