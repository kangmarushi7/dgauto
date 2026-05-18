"""List player_simulations JSON files."""
from __future__ import annotations

import json
import urllib.request

BASE = "https://www.datagaffer.com/player_simulations/"

CANDIDATES = [
    "all_teams.json",
    "fixture.json",
    "fixtures.json",
    "today.json",
    "match.json",
    "players.json",
    "lineups.json",
]


def main() -> None:
    for name in CANDIDATES:
        url = BASE + name
        try:
            with urllib.request.urlopen(url, timeout=8) as resp:
                raw = resp.read(200)
                print("OK", name, raw[:80])
        except Exception:
            pass

    # try team id paths from fixtures
    teams = json.load(urllib.request.urlopen("https://www.datagaffer.com/teams.json", timeout=15))
    for tid in [teams[0]["id"], teams[1]["id"]]:
        for pat in [f"{tid}.json", f"team_{tid}.json"]:
            url = BASE + pat
            try:
                with urllib.request.urlopen(url, timeout=8) as resp:
                    print("OK team path", pat, resp.read(100)[:80])
            except Exception:
                pass


if __name__ == "__main__":
    main()
