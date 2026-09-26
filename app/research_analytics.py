"""Research analytics — Main / Arahus / +EV profitability payloads for the dashboard."""
from __future__ import annotations

import json
import logging
import math
import re
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.auto_resolve import _compute_pnl
from app.bet_scenarios import scenario_meta_for_entry
from app.db import engine, list_bets
from app.seasons import fixture_date_ist

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CACHE_JSON = DATA_DIR / "research_analysis.json"
CACHE_MD = DATA_DIR / "research_report.md"
CACHE_PDF = DATA_DIR / "research_report.pdf"
STATUS_JSON = DATA_DIR / "research_status.json"

IST = ZoneInfo("Asia/Kolkata")
BUCKET_ORDER = [
    "1.00-1.29",
    "1.30-1.49",
    "1.50-1.69",
    "1.70-1.99",
    "2.00-2.49",
    "2.50-3.49",
    "3.50+",
    "missing",
]
STRATEGIES = (("main", "main"), ("arahus", "arahus"), ("ev", "ev"))
STRATEGY_LABEL = {"main": "Main", "arahus": "Arahus", "ev": "+EV", "combined": "Combined"}
MAIN_FOCUS = [
    "over_1.5",
    "over_2.5",
    "team_o0.5",
    "team_o1.5",
    "moneyline",
    "btts",
    "win_or_draw",
    "over_3.5",
]

_refresh_lock = threading.Lock()


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def classify_market(market: str, bet_type: str = "") -> str:
    """Team overs before match overs ('Team Over 1.5 Goals' contains 'over 1.5')."""
    bt = _norm(bet_type)
    t = _norm(f"{bet_type} {market}")
    if "corner" in t:
        return "corners"
    if "sot" in t or "shots on target" in t or "shot on target" in t:
        return "sot"
    if re.search(r"\bshots?\b", t) and "on target" not in t:
        return "shots"
    if "btts" in t or "both teams" in t:
        return "btts"
    if (
        "under 3.5" in t
        or "under3.5" in t
        or bt.startswith("u35")
        or re.search(r"\bu35\b", bt)
    ):
        return "under_3.5"
    if (
        "under 2.5" in t
        or "under2.5" in t
        or bt.startswith("u25")
        or re.search(r"\bu25\b", bt)
    ):
        return "under_2.5"
    if (
        "team o1.5" in t
        or "team over 1.5" in t
        or "team_o1" in bt
        or bt.startswith("to15")
        or re.search(r"\bto15\b", bt)
    ):
        return "team_o1.5"
    if (
        "team o0.5" in t
        or "team over 0.5" in t
        or "team_o0" in bt
        or bt.startswith("to05")
        or re.search(r"\bto05\b", bt)
    ):
        return "team_o0.5"
    if (
        "over 3.5" in t
        or "over3.5" in t
        or bt.startswith("o35")
        or re.search(r"\bo35\b", bt)
    ):
        return "over_3.5"
    if (
        "over 2.5" in t
        or "over2.5" in t
        or bt.startswith("o25")
        or re.search(r"\bo25\b", bt)
    ):
        return "over_2.5"
    if "over 1.5" in t or "over1.5" in t or bt.startswith("o15"):
        return "over_1.5"
    if re.search(r"\bo1\.5\b", t):
        return "team_o1.5" if "team" in t else "over_1.5"
    if re.search(r"\bo0\.5\b", t):
        return "team_o0.5" if "team" in t else "other"
    if "dc x2" in t or "dc_x2" in t or bt.startswith("dc_x2"):
        return "dc_x2"
    if (
        "dc 1x" in t
        or "dc_1x" in t
        or "win or draw" in t
        or bt.startswith("dc_win")
        or bt.startswith("dc_1x")
    ):
        return "win_or_draw"
    if t.strip() == "draw" or (re.search(r"\bdraw\b", t) and "win or draw" not in t):
        return "draw"
    if (
        "moneyline" in t
        or "win outright" in t
        or bt.startswith("ml_")
        or bt == "moneyline"
        or re.search(r"\bwin\b", t)
    ):
        return "moneyline"
    if "not to win" in t or "not_win" in t:
        return "not_win"
    return "other"


def odds_bucket(odds: float | None) -> str:
    if odds is None or (isinstance(odds, float) and math.isnan(odds)) or odds <= 0:
        return "missing"
    if odds < 1.30:
        return "1.00-1.29"
    if odds < 1.50:
        return "1.30-1.49"
    if odds < 1.70:
        return "1.50-1.69"
    if odds < 2.00:
        return "1.70-1.99"
    if odds < 2.50:
        return "2.00-2.49"
    if odds < 3.50:
        return "2.50-3.49"
    return "3.50+"


def agg(subset: list[dict[str, Any]]) -> dict[str, Any]:
    if not subset:
        return {
            "n": 0,
            "won": 0,
            "lost": 0,
            "push": 0,
            "win_pct": None,
            "pnl_units": 0.0,
            "roi_pct": None,
            "avg_odds": None,
            "staked": 0.0,
        }
    won = sum(1 for r in subset if r["result"] == "won")
    lost = sum(1 for r in subset if r["result"] == "lost")
    push = sum(1 for r in subset if r["result"] == "push")
    decided = won + lost
    staked = sum(float(r.get("units") or 0) for r in subset)
    pnl = sum(float(r.get("pnl_units") or 0) for r in subset)
    odds_vals = [float(r["odds"]) for r in subset if r.get("odds")]
    return {
        "n": len(subset),
        "won": won,
        "lost": lost,
        "push": push,
        "win_pct": round(100.0 * won / decided, 1) if decided else None,
        "pnl_units": round(pnl, 2),
        "roi_pct": round(100.0 * pnl / staked, 1) if staked else None,
        "avg_odds": round(sum(odds_vals) / len(odds_vals), 3) if odds_vals else None,
        "staked": round(staked, 2),
    }


def _write_status(status: str, **extra: Any) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"status": status, "updated_at": datetime.now(IST).isoformat(), **extra}
    STATUS_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_status() -> dict[str, Any]:
    if not STATUS_JSON.exists() and not CACHE_JSON.exists():
        return {"status": "never_run", "generated_at": None}
    if STATUS_JSON.exists():
        try:
            return json.loads(STATUS_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass
    if CACHE_JSON.exists():
        try:
            raw = json.loads(CACHE_JSON.read_text(encoding="utf-8"))
            return {
                "status": "ready",
                "generated_at": raw.get("meta", {}).get("generated_at"),
            }
        except Exception:
            return {"status": "error", "error": "corrupt_cache"}
    return {"status": "never_run", "generated_at": None}


def load_cached_payload() -> dict[str, Any] | None:
    if not CACHE_JSON.exists():
        return None
    try:
        return json.loads(CACHE_JSON.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read research cache: %s", exc)
        return None


def _load_rows(log_type: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for r in list_bets(log_type):
        st = str(r.get("status") or "").strip().lower()
        if st not in {"won", "lost", "push", "open"}:
            st = "open"
        bet_type = str(r.get("bet_type") or "")
        team = str(r.get("team_name") or "")
        meta = scenario_meta_for_entry(r)
        mlabel = str(meta.get("label") or bet_type or "")
        market = (
            f"{team} · {mlabel}"
            if team and team.lower() not in mlabel.lower()
            else (mlabel or bet_type)
        )
        mclass = classify_market(market, bet_type)
        if mclass == "other":
            mclass = classify_market(bet_type, bet_type)
        odds = float(r.get("odds") or 0) or None
        units = 1.0 if log_type == "ev" else float(r.get("units") or 1.0)
        pnl = r.get("pnl_units")
        if st in {"won", "lost", "push"}:
            if pnl is None:
                pnl = _compute_pnl({"odds": odds or 0, "units": units, "log_type": log_type}, st)
            else:
                pnl = float(pnl)
        else:
            pnl = None
        d = fixture_date_ist(r)
        rows.append(
            {
                "strategy_key": log_type,
                "market_class": mclass,
                "league": str(r.get("league_name") or "") or "(unknown)",
                "odds": odds,
                "units": units,
                "result": st if st in {"won", "lost", "push"} else "open",
                "pnl_units": pnl,
                "day": d,
            }
        )
    return rows


def _settled(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["result"] in {"won", "lost", "push"}]


def _group(rows: list[dict], key_fn, *, order: list[str] | None = None, min_n: int = 1) -> list[dict]:
    buckets: dict[str, list] = defaultdict(list)
    for r in rows:
        buckets[str(key_fn(r) or "(unknown)")].append(r)
    if order:
        keys = [k for k in order if k in buckets] + [k for k in buckets if k not in order]
    else:
        keys = sorted(buckets.keys(), key=lambda k: (-len(buckets[k]), k))
    out = []
    for k in keys:
        subset = buckets[k]
        if len(subset) < min_n:
            continue
        a = agg(subset)
        a["key"] = k
        out.append(a)
    if not order:
        out.sort(key=lambda x: (x["pnl_units"], x["n"]), reverse=True)
    return out


def _rolling(rows: list[dict], days: int, asof: date) -> list[dict]:
    cutoff = asof - timedelta(days=days - 1)
    return [r for r in rows if r.get("day") and cutoff <= r["day"] <= asof]


def _market_odds(rows: list[dict], markets: list[str]) -> list[dict]:
    out = []
    for m in markets:
        subset = [r for r in rows if r["market_class"] == m]
        if not subset:
            continue
        overall = agg(subset)
        overall["key"] = m
        out.append(
            {
                "market": m,
                "overall": overall,
                "by_odds": _group(subset, lambda r: odds_bucket(r.get("odds")), order=BUCKET_ORDER),
            }
        )
    return out


def _analyze(rows: list[dict], key: str, asof: date) -> dict[str, Any]:
    s = _settled(rows)
    by_market = _group(s, lambda r: r["market_class"])
    by_odds = _group(s, lambda r: odds_bucket(r.get("odds")), order=BUCKET_ORDER)
    by_league = _group(s, lambda r: r["league"])
    by_league_vol = sorted(by_league, key=lambda x: x["n"], reverse=True)[:20]
    by_league_roi = [
        x
        for x in sorted(by_league, key=lambda x: (x.get("roi_pct") or -999, x["n"]), reverse=True)
        if x["n"] >= 15
    ][:15]
    rolling = {}
    for d in (25, 50, 100):
        a = agg(_rolling(s, d, asof))
        a["key"] = f"last_{d}d"
        rolling[f"{d}d"] = a

    if key == "main":
        focus = [m for m in MAIN_FOCUS if any(r["market_class"] == m for r in s)]
    else:
        focus = [a["key"] for a in by_market[:8]]

    keep = []
    cut = []
    for a in by_market:
        if a["n"] >= 25 and (a.get("roi_pct") or -999) >= 3:
            keep.append({"scope": f"market:{a['key']}", "n": a["n"], "roi_pct": a["roi_pct"], "pnl_units": a["pnl_units"]})
        if a["n"] >= 40 and (a.get("roi_pct") or 0) <= -5:
            cut.append({"scope": f"market:{a['key']}", "n": a["n"], "roi_pct": a["roi_pct"], "pnl_units": a["pnl_units"]})
    for a in by_odds:
        if a["key"] == "missing":
            continue
        if a["n"] >= 25 and (a.get("roi_pct") or -999) >= 3:
            keep.append({"scope": f"odds:{a['key']}", "n": a["n"], "roi_pct": a["roi_pct"], "pnl_units": a["pnl_units"]})
        if a["n"] >= 40 and (a.get("roi_pct") or 0) <= -8:
            cut.append({"scope": f"odds:{a['key']}", "n": a["n"], "roi_pct": a["roi_pct"], "pnl_units": a["pnl_units"]})
    for a in by_league_roi:
        if (a.get("roi_pct") or -999) >= 5:
            keep.append({"scope": f"league:{a['key']}", "n": a["n"], "roi_pct": a["roi_pct"], "pnl_units": a["pnl_units"]})
    keep.sort(key=lambda x: (x.get("roi_pct") or 0, x["pnl_units"]), reverse=True)
    cut.sort(key=lambda x: (x.get("roi_pct") or 0, x["pnl_units"]))

    return {
        "key": key,
        "label": STRATEGY_LABEL.get(key, key),
        "open_n": sum(1 for r in rows if r["result"] == "open"),
        "overall": agg(s),
        "by_market": by_market,
        "by_odds": by_odds,
        "by_league_volume": by_league_vol,
        "by_league_roi": by_league_roi,
        "rolling": rolling,
        "market_odds": _market_odds(s, focus),
        "keep": keep[:20],
        "cut": cut[:15],
    }


def _consensus(slices: dict[str, dict]) -> list[dict]:
    market_hits: dict[str, list] = defaultdict(list)
    odds_hits: dict[str, list] = defaultdict(list)
    league_hits: dict[str, list] = defaultdict(list)
    for key, sl in slices.items():
        if key == "combined":
            continue
        label = sl["label"]
        for a in sl["by_market"]:
            if a["n"] >= 20 and (a.get("roi_pct") or -999) >= 2:
                market_hits[a["key"]].append((label, a))
        for a in sl["by_odds"]:
            if a["key"] == "missing":
                continue
            if a["n"] >= 25 and (a.get("roi_pct") or -999) >= 2:
                odds_hits[a["key"]].append((label, a))
        for a in sl["by_league_volume"]:
            if a["n"] >= 20 and (a.get("roi_pct") or -999) >= 5:
                league_hits[a["key"]].append((label, a))

    out = []
    for kind, bag in (("market", market_hits), ("odds", odds_hits), ("league", league_hits)):
        for name, hits in bag.items():
            if len(hits) < 2:
                continue
            out.append(
                {
                    "angle": f"{kind}:{name}",
                    "strategies": ", ".join(h[0] for h in hits),
                    "detail": "; ".join(
                        f"{h[0]} n={h[1]['n']} ROI={_fmt_num(h[1].get('roi_pct'), '+.1f')}% "
                        f"PnL={_fmt_num(h[1].get('pnl_units'), '+.1f')}"
                        for h in hits
                    ),
                }
            )

    main = slices.get("main")
    if main:
        # durable Main markets from market_odds overall + rolling
        # Rebuild quickly from by_market + need settled rows — use market_odds overall + approximate via rolling on full main
        for block in main.get("market_odds") or []:
            m = block["market"]
            overall = block["overall"]
            if overall["n"] < 40 or (overall.get("roi_pct") or -999) < 2:
                continue
            out.append(
                {
                    "angle": f"Main durable market:{m}",
                    "strategies": "Main",
                    "detail": (
                        f"all-time ROI {_fmt_num(overall.get('roi_pct'), '+.1f')}% "
                        f"({_fmt_num(overall.get('pnl_units'), '+.1f')}u, n={overall['n']})"
                    ),
                }
            )
    return out


def _fmt_num(value: Any, spec: str = "+.2f", empty: str = "—") -> str:
    if value is None:
        return empty
    try:
        return format(float(value), spec)
    except (TypeError, ValueError):
        return empty


def _md_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        cells = []
        for c in row:
            if c is None:
                cells.append("—")
            else:
                cells.append(str(c))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def _fmt_agg_table(items: list[dict], key_header: str) -> list[str]:
    rows = []
    for a in items:
        rows.append(
            [
                a["key"],
                a["n"],
                a.get("win_pct"),
                _fmt_num(a.get("pnl_units"), "+.2f"),
                _fmt_num(a.get("roi_pct"), "+.1f"),
                _fmt_num(a.get("avg_odds"), ".3f"),
            ]
        )
    return _md_table([key_header, "N", "Win%", "PnL(u)", "ROI%", "AvgOdds"], rows)


def _fmt_playbook_item(item: dict[str, Any]) -> str:
    scope = item.get("scope") or ""
    strategy = item.get("strategy") or ""
    if item.get("detail"):
        return f"- **{scope}** ({strategy}): {item['detail']}"
    return (
        f"- **{scope}** ({strategy}): "
        f"n={item.get('n') if item.get('n') is not None else '—'}, "
        f"ROI {_fmt_num(item.get('roi_pct'), '+.1f')}%, "
        f"PnL {_fmt_num(item.get('pnl_units'), '+.1f')}u"
    )


def _write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines: list[str] = []
    meta = payload["meta"]
    lines.append("# Research profitability report")
    lines.append("")
    lines.append(f"Generated: `{meta.get('generated_at')}`")
    lines.append("")
    lines.append("## Executive summary")
    lines.append("")
    sum_rows = []
    for key in ("main", "arahus", "ev", "combined"):
        sl = payload["slices"][key]
        o = sl["overall"]
        sum_rows.append(
            [
                sl["label"],
                o["n"],
                o.get("win_pct"),
                _fmt_num(o.get("pnl_units"), "+.2f"),
                _fmt_num(o.get("roi_pct"), "+.1f"),
                sl["open_n"],
            ]
        )
    lines.extend(_md_table(["Strategy", "Settled", "Win%", "PnL", "ROI%", "Open"], sum_rows))
    lines.append("")

    for key in ("main", "arahus", "ev", "combined"):
        sl = payload["slices"][key]
        o = sl["overall"]
        lines.append(f"## {sl['label']}")
        lines.append("")
        lines.append(
            f"Settled **{o['n']}** · open {sl['open_n']} · win {_fmt_num(o.get('win_pct'), '.1f')}% · "
            f"PnL **{_fmt_num(o.get('pnl_units'), '+.2f')}u** · ROI **{_fmt_num(o.get('roi_pct'), '+.1f')}%**"
        )
        lines.append("")
        lines.append("### Markets")
        lines.append("")
        lines.extend(_fmt_agg_table(sl["by_market"], "Market"))
        lines.append("")
        lines.append("### Odds")
        lines.append("")
        lines.extend(_fmt_agg_table(sl["by_odds"], "Odds"))
        lines.append("")
        lines.append("### Leagues (volume)")
        lines.append("")
        lines.extend(_fmt_agg_table(sl["by_league_volume"], "League"))
        lines.append("")
        lines.append("### Rolling")
        lines.append("")
        roll_rows = []
        for d in (25, 50, 100):
            a = sl["rolling"][f"{d}d"]
            roll_rows.append(
                [
                    f"last {d}d",
                    a["n"],
                    _fmt_num(a.get("pnl_units"), "+.2f"),
                    _fmt_num(a.get("roi_pct"), "+.1f"),
                ]
            )
        lines.extend(_md_table(["Window", "N", "PnL", "ROI%"], roll_rows))
        lines.append("")
        if sl.get("market_odds"):
            lines.append("### Focus markets x odds")
            lines.append("")
            for block in sl["market_odds"]:
                lines.append(f"#### {block['market']}")
                lines.append("")
                lines.extend(_fmt_agg_table(block["by_odds"], "Odds"))
                lines.append("")

    lines.append("## Cross-strategy durable angles")
    lines.append("")
    cons = payload.get("consensus") or []
    if not cons:
        lines.append("None at current thresholds.")
    else:
        lines.extend(
            _md_table(
                ["Angle", "Strategies", "Detail"],
                [[c["angle"], c["strategies"], c["detail"]] for c in cons],
            )
        )
    lines.append("")
    lines.append("## Playbook keep")
    lines.append("")
    for item in payload.get("playbook_keep") or []:
        lines.append(_fmt_playbook_item(item))
    lines.append("")
    lines.append("## Playbook cut")
    lines.append("")
    for item in payload.get("playbook_cut") or []:
        lines.append(_fmt_playbook_item(item))
    lines.append("")

    live = payload.get("live_buckets") or {}
    cats = live.get("categories") or {}
    if cats:
        lines.append("## Capital buckets (LIVE / TRACKING / LOGGING)")
        lines.append("")
        lines.append(f"Flat stake: `${live.get('flat_stake_usd', 1.0):.2f}` USD")
        lines.append("")
        bucket_rows = []
        for cid, info in cats.items():
            roi = info.get("roi_full")
            bucket_rows.append(
                [
                    cid,
                    info.get("state"),
                    info.get("n"),
                    _fmt_num((roi * 100) if roi is not None else None, "+.1f"),
                    "pass" if info.get("graduation_all_pass") else "fail",
                ]
            )
        lines.extend(_md_table(["Category", "State", "N", "ROI%", "Gates"], bucket_rows))
        lines.append("")
        live_pnl = payload.get("live_pnl") or {}
        if live_pnl:
            lines.append(
                f"LIVE aggregate: n={live_pnl.get('n')} · "
                f"PnL {_fmt_num(live_pnl.get('pnl'), '+.2f')}u · "
                f"ROI {_fmt_num((live_pnl.get('roi') or 0) * 100 if live_pnl.get('roi') is not None else None, '+.1f')}%"
            )
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def build_research_payload() -> dict[str, Any]:
    now = datetime.now(IST)
    asof = now.date()
    try:
        engine.dispose()
    except Exception:
        pass

    by_key: dict[str, list] = {}
    for log_type, _ in STRATEGIES:
        by_key[log_type] = _load_rows(log_type)

    slices = {
        "main": _analyze(by_key["main"], "main", asof),
        "arahus": _analyze(by_key["arahus"], "arahus", asof),
        "ev": _analyze(by_key["ev"], "ev", asof),
        "combined": _analyze(by_key["main"] + by_key["arahus"] + by_key["ev"], "combined", asof),
    }
    consensus = _consensus(slices)

    playbook_keep = []
    playbook_cut = []
    for key in ("main", "arahus", "ev"):
        for item in slices[key]["keep"][:8]:
            playbook_keep.append({**item, "strategy": slices[key]["label"]})
        for item in slices[key]["cut"][:6]:
            playbook_cut.append({**item, "strategy": slices[key]["label"]})
    for c in consensus:
        playbook_keep.insert(0, {
            "scope": c["angle"],
            "strategy": c["strategies"],
            "n": None,
            "roi_pct": None,
            "pnl_units": None,
            "detail": c["detail"],
        })

    # Single source of truth for LIVE / TRACKING / LOGGING capital buckets.
    from app.strategy_buckets import (
        LIVE_CATEGORY_IDS,
        aggregate_live_pnl,
        category_status_report,
        load_pipeline_bets_from_db,
    )

    try:
        bucket_rows = load_pipeline_bets_from_db()
        # Ensure Main/Arahus/+EV research rows are included even if cs/h2h empty.
        for key, log_type in (("main", "main"), ("arahus", "arahus"), ("ev", "ev")):
            if not bucket_rows.get(log_type):
                bucket_rows[log_type] = [
                    {**r, "strategy": log_type, "log_type": log_type} for r in by_key[key]
                ]
        live_buckets = category_status_report(bucket_rows)
        flat_for_pnl = []
        for strat, rows in bucket_rows.items():
            flat_for_pnl.extend({**r, "strategy": r.get("strategy") or strat} for r in rows)
        live_pnl = aggregate_live_pnl(flat_for_pnl)
    except Exception as exc:
        logger.warning("strategy_buckets report failed: %s", exc)
        live_buckets = {"error": str(exc), "categories": {}}
        live_pnl = {}

    return {
        "meta": {
            "generated_at": now.isoformat(timespec="seconds"),
            "asof": asof.isoformat(),
            "sources": ["db:main", "db:arahus", "db:ev"],
            "classifier": "team_overs_before_match_overs",
            "live_category_ids": list(LIVE_CATEGORY_IDS),
        },
        "slices": slices,
        "consensus": consensus,
        "playbook_keep": playbook_keep[:25],
        "playbook_cut": playbook_cut[:20],
        "live_buckets": live_buckets,
        "live_pnl": live_pnl,
    }


def refresh_research_cache() -> dict[str, Any]:
    """Rebuild analysis cache + MD/PDF. Thread-safe; raises on failure."""
    if not _refresh_lock.acquire(blocking=False):
        raise RuntimeError("Research refresh already running")
    started = time.monotonic()
    try:
        _write_status("running")
        payload = build_research_payload()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_JSON.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        _write_markdown(payload, CACHE_MD)
        try:
            from scripts.md_report_to_pdf import render_md_to_pdf

            render_md_to_pdf(CACHE_MD, CACHE_PDF)
        except Exception as exc:
            logger.warning("Research PDF render failed: %s", exc)
            # MD/JSON still valid
        elapsed = round(time.monotonic() - started, 2)
        _write_status(
            "ready",
            generated_at=payload["meta"]["generated_at"],
            elapsed_sec=elapsed,
            artifacts={"json": str(CACHE_JSON), "md": str(CACHE_MD), "pdf": str(CACHE_PDF)},
        )
        payload["meta"]["elapsed_sec"] = elapsed
        return payload
    except Exception as exc:
        _write_status("error", error=str(exc))
        raise
    finally:
        _refresh_lock.release()


def get_research_api_response() -> dict[str, Any]:
    status = read_status()
    data = load_cached_payload()
    return {
        "ok": True,
        "status": status.get("status") or ("ready" if data else "never_run"),
        "generated_at": (data or {}).get("meta", {}).get("generated_at") or status.get("generated_at"),
        "error": status.get("error"),
        "elapsed_sec": status.get("elapsed_sec"),
        "exports": {
            "md": CACHE_MD.exists(),
            "pdf": CACHE_PDF.exists(),
        },
        "data": data,
    }
