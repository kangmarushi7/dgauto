from __future__ import annotations

import urllib.request
from pathlib import Path

html = urllib.request.urlopen("https://www.datagaffer.com/goal_zone", timeout=20).read().decode("utf-8", "replace")
for term in ["correct", "matrix", "scoreGrid", "scoreProb", "buildScore", "renderScore"]:
    idx = 0
    while True:
        idx = html.lower().find(term.lower(), idx)
        if idx < 0:
            break
        snippet = html[max(0, idx - 40) : idx + 200]
        print("---", term, idx, "---")
        print(snippet.replace("\n", " ")[:200])
        idx += len(term)

Path(__file__).parent.joinpath("goal_zone_full.html").write_text(html, encoding="utf-8")
