"""Model-backed filters for +EV fixture markets (edge/EV alone is not enough)."""
from __future__ import annotations

import re
from typing import Any

from app.fixture_math import num

# Minimum xG / total projection above the betting line (Poisson margin).
TEAM_O15_MIN_XG = 1.85
TEAM_O05_MIN_XG = 1.05
TOTAL_O15_MIN_XG = 2.2
TOTAL_O25_MIN_XG = 2.85
TOTAL_O35_MIN_XG = 3.65
TOTAL_U25_MAX_XG = 2.35
BTTS_MIN_TEAM_XG = 0.95
WIN_MIN_XG_EDGE = 0.25
DC_MIN_XG_EDGE = -0.15


def _parse_team_line(market: str, home_name: str, away_name: str) -> tuple[str | None, float | None]:
    """Return (team_name, line) for '{Team} O1.5' style labels."""
    m = market.strip()
    for team in (home_name, away_name):
        if not team:
            continue
        for pattern, line in (
            (rf"^{re.escape(team)}\s+O1\.5$", 1.5),
            (rf"^{re.escape(team)}\s+O0\.5$", 0.5),
            (rf"^{re.escape(team)}\s+O1\.5\s+Goals$", 1.5),
        ):
            if re.match(pattern, m, re.I):
                return team, line
    return None, None


def resolve_kind_for_market(market: str, home_name: str, away_name: str) -> tuple[str, str | None]:
    """Map dashboard market label -> (bet_type slug, team_name)."""
    mk = market.strip()
    team, line = _parse_team_line(mk, home_name, away_name)
    if team and line == 1.5:
        return "team_o1.5", team
    if team and line == 0.5:
        return "team_o0.5", team

    low = mk.lower()
    if low == "draw":
        return "draw", None
    if low == "btts yes":
        return "btts", None
    if low == "over 1.5":
        return "over1.5", None
    if low == "over 2.5":
        return "over2.5", None
    if low == "over 3.5":
        return "over3.5", None
    if low == "under 2.5":
        return "under2.5", None
    if low == "dc 1x":
        return "dc_1x", home_name
    if low == "dc x2":
        return "dc_x2", away_name
    if mk == f"{home_name} Win":
        return "moneyline", home_name
    if mk == f"{away_name} Win":
        return "moneyline", away_name
    return "unknown", None


def market_passes_model_filter(
    market: str,
    *,
    home_name: str,
    away_name: str,
    xg: dict[str, Any],
    perc: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """
    Return (passes, reason). Uses projected xG from sim — not just sim win %.
    """
    perc = perc or {}
    hx = num(xg.get("home"))
    ax = num(xg.get("away"))
    tx = num(xg.get("total"))
    if tx is None and hx is not None and ax is not None:
        tx = hx + ax

    team, line = _parse_team_line(market, home_name, away_name)
    if team and line == 1.5:
        team_xg = hx if team == home_name else ax
        if team_xg is None:
            return False, "missing team xG"
        if team_xg < TEAM_O15_MIN_XG:
            return False, f"team xG {team_xg:.2f} below {TEAM_O15_MIN_XG} for O1.5"
        return True, ""

    if team and line == 0.5:
        team_xg = hx if team == home_name else ax
        if team_xg is None:
            return False, "missing team xG"
        if team_xg < TEAM_O05_MIN_XG:
            return False, f"team xG {team_xg:.2f} too low for O0.5"
        return True, ""

    low = market.strip().lower()
    if low == "over 1.5":
        if tx is None or tx < TOTAL_O15_MIN_XG:
            return False, f"total xG {tx} below {TOTAL_O15_MIN_XG} for Over 1.5"
        return True, ""
    if low == "over 2.5":
        if tx is None or tx < TOTAL_O25_MIN_XG:
            return False, f"total xG {tx} below {TOTAL_O25_MIN_XG} for Over 2.5"
        return True, ""
    if low == "over 3.5":
        if tx is None or tx < TOTAL_O35_MIN_XG:
            return False, f"total xG {tx} below {TOTAL_O35_MIN_XG} for Over 3.5"
        return True, ""
    if low == "under 2.5":
        if tx is None or tx > TOTAL_U25_MAX_XG:
            return False, f"total xG {tx} above {TOTAL_U25_MAX_XG} for Under 2.5"
        return True, ""
    if low == "btts yes":
        if hx is None or ax is None:
            return False, "missing team xG for BTTS"
        if min(hx, ax) < BTTS_MIN_TEAM_XG:
            return False, f"both teams need xG ≥ {BTTS_MIN_TEAM_XG} (got {hx:.2f}/{ax:.2f})"
        return True, ""

    if market == f"{home_name} Win":
        if hx is None or ax is None:
            return False, "missing xG for moneyline"
        if hx < ax + WIN_MIN_XG_EDGE:
            return False, f"home xG {hx:.2f} lacks edge vs away {ax:.2f}"
        return True, ""

    if market == f"{away_name} Win":
        if hx is None or ax is None:
            return False, "missing xG for moneyline"
        if ax < hx + WIN_MIN_XG_EDGE:
            return False, f"away xG {ax:.2f} lacks edge vs home {hx:.2f}"
        return True, ""

    if low == "draw":
        draw_pct = num(perc.get("draw_pct"))
        if draw_pct is not None and draw_pct < 26:
            return False, f"draw model {draw_pct:.0f}% too low"
        if hx is not None and ax is not None and abs(hx - ax) > 0.45:
            return False, "xG profile not draw-shaped"
        return True, ""

    if low == "dc 1x":
        if hx is None or ax is None:
            return False, "missing xG for DC 1X"
        if hx < ax + DC_MIN_XG_EDGE:
            return False, "home not competitive enough for 1X"
        return True, ""

    if low == "dc x2":
        if hx is None or ax is None:
            return False, "missing xG for DC X2"
        if ax < hx + DC_MIN_XG_EDGE:
            return False, "away not competitive enough for X2"
        return True, ""

    return False, "unsupported or unpriced market"


def is_actionable_plus_ev_market(
    m: dict[str, Any],
    *,
    home_name: str,
    away_name: str,
    xg: dict[str, Any],
    perc: dict[str, Any] | None = None,
) -> bool:
    """Positive EV + edge verdict + model projection supports the bet."""
    edge = num(m.get("edge"))
    ev = num(m.get("ev"))
    verdict = str(m.get("verdict") or "")
    if edge is None or edge < 2 or ev is None or ev <= 0:
        return False
    if verdict not in ("STRONG VALUE", "VALUE", "LEAN"):
        return False
    ok, _ = market_passes_model_filter(
        str(m.get("market") or ""),
        home_name=home_name,
        away_name=away_name,
        xg=xg,
        perc=perc,
    )
    return ok
