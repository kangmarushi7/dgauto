from __future__ import annotations

from pydantic import BaseModel, Field


class MatchSignal(BaseModel):
    fixture: str
    fixture_id: int | None = None
    home_team: str = ""
    away_team: str = ""
    home_team_id: int | None = None
    away_team_id: int | None = None
    fixture_date: str | None = None
    league_name: str = ""
    win_pct: float | None = None
    draw_pct: float | None = None
    away_win_pct: float | None = None
    home_ml_odds: float | None = None
    away_ml_odds: float | None = None
    over_1_5_odds: float | None = None
    over_25_pct: float | None = None
    btts_pct: float | None = None
    home_projected_goals: float | None = None
    away_projected_goals: float | None = None
    projected_total_goals: float | None = None
    score: float = 0.0
    signal: str = "watch"


class RefreshResponse(BaseModel):
    success: bool
    message: str
    scraped_at: str | None = None
    matches: list[MatchSignal] = Field(default_factory=list)
