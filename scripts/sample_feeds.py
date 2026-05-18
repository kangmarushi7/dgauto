from __future__ import annotations

import json
import urllib.request


def main() -> None:
    h2h = json.load(urllib.request.urlopen("https://www.datagaffer.com/head2head.json", timeout=15))
    print("h2h keys", h2h[0].keys())
    print("versus_grades", json.dumps(h2h[0].get("versus_grades"), indent=2)[:500])

    heat = json.load(urllib.request.urlopen("https://www.datagaffer.com/projected_heat_stats.json", timeout=15))
    m = heat["matches"][0]
    print("heat projected_stats keys", m["projected_stats"].keys())
    print(json.dumps(m["projected_stats"], indent=2)[:600])

    tp = json.load(urllib.request.urlopen("https://www.datagaffer.com/top_picks.json", timeout=15))
    today = tp.get("today") or []
    print("top_picks today count", len(today))
    if today:
        print(json.dumps(today[0], indent=2)[:500])

    pf = json.load(urllib.request.urlopen("https://www.datagaffer.com/player_form.json", timeout=15))
    print("player_form type", type(pf), "keys" if isinstance(pf, dict) else len(pf))


if __name__ == "__main__":
    main()
