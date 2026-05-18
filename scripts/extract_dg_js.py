"""Extract Supabase and page routes from DataGaffer HTML."""
from __future__ import annotations

import re
import urllib.request

FID = 1494170
PAGES = [
    f"/dashboard?fixture_id={FID}",
    "/sim_cards",
    "/head2head",
    "/player_simulations",
    "/heat_maps",
    "/correct_score",
    "/projections",
    "/plays",
]

BASE = "https://www.datagaffer.com"


def scan(path: str) -> None:
    url = BASE + path
    html = urllib.request.urlopen(url, timeout=20).read().decode("utf-8", "replace")
    print(f"\n=== {path} ({len(html)} bytes) ===")
    jsons = sorted(set(re.findall(r'["\']([/a-zA-Z0-9_\-./]+\.json)["\']', html)))
    if jsons:
        print("json:", jsons)
    tables = sorted(set(re.findall(r'\.from\(["\']([^"\']+)["\']\)', html)))
    if tables:
        print("supabase tables:", tables)
    rpcs = sorted(set(re.findall(r'\.rpc\(["\']([^"\']+)["\']', html)))
    if rpcs:
        print("rpc:", rpcs)
    routes = sorted(
        set(
            re.findall(
                r'href=["\'](/(?:sim_cards|head2head|player_simulations|heat_maps|correct_score|projections|plays|corner_zone|parlay)[^"\']*)["\']',
                html,
            )
        )
    )
    if routes:
        print("routes:", routes[:20])


def main() -> None:
    for p in PAGES:
        try:
            scan(p)
        except Exception as e:
            print(f"\n=== {p} FAIL: {e} ===")


if __name__ == "__main__":
    main()
