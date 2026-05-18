"""Probe fixture page URL patterns on DataGaffer."""
from __future__ import annotations

import urllib.request

FID = 1494170
PATHS = [
    f"/fixture/{FID}",
    f"/fixtures/{FID}",
    f"/match/{FID}",
    f"/match_sim/{FID}",
    f"/sim/{FID}",
    f"/dashboard?fixture={FID}",
    f"/dashboard?fixture_id={FID}",
    f"/goal_zone?fixture={FID}",
    f"/goal_zone/{FID}",
    f"/full_time/{FID}",
    f"/player_sims/{FID}",
    f"/correct_score/{FID}",
    f"/heat_maps/{FID}",
    f"/head2head/{FID}",
    f"/sim_cards/{FID}",
]

BASE = "https://www.datagaffer.com"


def main() -> None:
    for p in PATHS:
        url = BASE + p
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=10) as resp:
                print(resp.status, p, resp.url)
        except urllib.error.HTTPError as e:
            print(e.code, p)
        except Exception as e:
            print("ERR", p, e)


if __name__ == "__main__":
    main()
