# Flashscore ninja feed — settlement / live scores
# Primary settle path for open bets (see BET_SETTLE_SOURCE).

## Feed URL

```
https://global.flashscore.ninja/2/x/feed/f_{sport}_{dayOffset}_3_en_1
```

- `sport`: `1` football, `2` tennis
- `dayOffset`: `0` today, `-1` yesterday, `1` tomorrow, …

Required header: `X-Fsign` (env `FLASHSCORE_FSIGN`, default `SW9D1eZo`).
If the body is empty after HTTP 200, the FSIGN has likely rotated — update the env var.

## Separators

| Role | Char | Unicode |
|------|------|---------|
| Row  | `~`  |         |
| Cell | `¬`  | U+00AC  |
| Key/value | `÷` | U+00F7 |

## Critical fields

| Key | Football | Tennis |
|-----|----------|--------|
| AA | match id | match id |
| CX / AF | home / away | player1 / player2 |
| AG / AH | goals | current games |
| AB | 1 sched, 2 live, 3 FT, 4/5 ppd/can | stage |
| AI | live flag `y` | live flag `y` |
| AD | kickoff unix | kickoff unix |
| WU / WV | URL slugs | URL slugs |
| BA–BJ | — | set games |

## Day offsets (settlement)

Default settlement window: **−10 … +2** (`FLASHSCORE_DAY_OFFSETS`).
Auto-resolve also expands offsets from each open bet’s `fixture_date` so
Allsvenskan / Eliteserien / Liga MX / Superliga weekend cards are included.

Flashscore often returns empty bodies beyond ~7–8 days — that is retention, not an FSIGN failure.

## Matching

Normalize → tokens length ≥ 3 (drop `fc`/`club`/etc.) → **both** home and away must overlap.
League hints (Sweden/Norway/Mexico/Denmark) rank candidates and reject wrong countries
(e.g. Romania Superliga when settling Danish Superliga). Youth/reserve/women are penalized.

## Python API

```python
from app.flashscore_client import (
    refresh_cache,
    find_match,
    score_for_fixture,
    score_for_players,
    finished_winner_for_settlement,
)

refresh_cache(force=True)
score_for_fixture("Hammarby", "Kalmar FF", league="Allsvenskan")
```

Settlement uses Flashscore first, then API-Football:

```env
BET_SETTLE_SOURCE=flashscore,api_football
FLASHSCORE_FSIGN=SW9D1eZo
FLASHSCORE_DAY_OFFSETS=-1,0,1,2
FLASHSCORE_CACHE_TTL_SEC=180
```

Core scores never depend on HTML scraping. Optional Playwright is football-only for minute/stats when explicitly enabled later.
