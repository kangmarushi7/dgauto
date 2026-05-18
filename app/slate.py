from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

OVER_15_GOALS_MIN = 3.51
MONEYLINE_MIN_WIN = 61.0
BTTS_MIN_TEAM_XG = 1.5


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _is_today_ist(dt: datetime | None) -> bool:
    if dt is None:
        return True
    local = dt.astimezone(IST)
    return local.date() == datetime.now(IST).date()


def _fmt_kickoff(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    local = dt.astimezone(IST)
    h = local.hour % 12 or 12
    minute = local.minute
    ampm = "AM" if local.hour < 12 else "PM"
    if minute:
        return f"{h}:{minute:02d} {ampm}"
    return f"{h} {ampm}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}%"


def _fmt_num(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}"


def _build_picks(m: dict[str, Any]) -> list[dict[str, str]]:
    picks: list[dict[str, str]] = []
    home_win = m.get("win_pct") or 0.0
    away_win = m.get("away_win_pct") or 0.0
    total_xg = m.get("projected_total_goals")
    home_xg = m.get("home_projected_goals")
    away_xg = m.get("away_projected_goals")
    home = m.get("home_team") or "Home"
    away = m.get("away_team") or "Away"

    if home_win > MONEYLINE_MIN_WIN:
        picks.append(
            {
                "kind": "moneyline",
                "label": f"{home} Win",
                "detail": _fmt_pct(home_win),
                "tone": "strong",
            }
        )
    if away_win > MONEYLINE_MIN_WIN:
        picks.append(
            {
                "kind": "moneyline",
                "label": f"{away} Win",
                "detail": _fmt_pct(away_win),
                "tone": "strong",
            }
        )

    if total_xg is not None and float(total_xg) >= OVER_15_GOALS_MIN:
        picks.append(
            {
                "kind": "goals",
                "label": "Over 1.5 Goals",
                "detail": f"Proj {_fmt_num(total_xg)}",
                "tone": "goals",
            }
        )

    if (
        home_xg is not None
        and away_xg is not None
        and float(home_xg) >= BTTS_MIN_TEAM_XG
        and float(away_xg) >= BTTS_MIN_TEAM_XG
    ):
        btts = m.get("btts_pct")
        picks.append(
            {
                "kind": "btts",
                "label": "BTTS Yes",
                "detail": _fmt_pct(btts) if btts is not None else "Both 1.5+ xG",
                "tone": "btts",
            }
        )

    over25 = m.get("over_25_pct")
    if over25 is not None and float(over25) >= 65:
        picks.append(
            {
                "kind": "over25",
                "label": "Over 2.5",
                "detail": _fmt_pct(over25),
                "tone": "goals",
            }
        )

    return picks


def build_fixture_slate(
    matches: list[dict[str, Any]],
    *,
    today_only: bool = True,
) -> list[dict[str, Any]]:
    """Fixture-centric slate for homepage (DataGaffer-style)."""
    slate: list[dict[str, Any]] = []

    for m in matches:
        dt = _parse_dt(m.get("fixture_date"))
        if today_only and not _is_today_ist(dt):
            continue

        picks = _build_picks(m)
        slate.append(
            {
                "fixture_id": m.get("fixture_id"),
                "fixture": m.get("fixture") or "",
                "home_team": m.get("home_team") or "",
                "away_team": m.get("away_team") or "",
                "home_logo": m.get("home_logo") or "",
                "away_logo": m.get("away_logo") or "",
                "league_name": m.get("league_name") or "",
                "fixture_date": m.get("fixture_date"),
                "kickoff": _fmt_kickoff(dt),
                "kickoff_sort": dt.timestamp() if dt else 0,
                "win_pct": m.get("win_pct"),
                "draw_pct": m.get("draw_pct"),
                "away_win_pct": m.get("away_win_pct"),
                "over_1_5_pct": m.get("over_1_5_pct"),
                "over_25_pct": m.get("over_25_pct"),
                "over_3_5_pct": m.get("over_3_5_pct"),
                "under_2_5_pct": m.get("under_2_5_pct"),
                "btts_pct": m.get("btts_pct"),
                "home_projected_goals": m.get("home_projected_goals"),
                "away_projected_goals": m.get("away_projected_goals"),
                "projected_total_goals": m.get("projected_total_goals"),
                "home_ml_odds": m.get("home_ml_odds"),
                "away_ml_odds": m.get("away_ml_odds"),
                "over_1_5_odds": m.get("over_1_5_odds"),
                "over_2_5_odds": m.get("over_2_5_odds"),
                "btts_yes_odds": m.get("btts_yes_odds"),
                "score": m.get("score"),
                "signal": m.get("signal") or "watch",
                "picks": picks,
                "has_picks": len(picks) > 0,
            }
        )

    slate.sort(key=lambda x: (x["kickoff_sort"], x["fixture"]))

    if today_only and not slate and matches:
        return build_fixture_slate(matches, today_only=False)

    return slate
