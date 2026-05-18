from __future__ import annotations

import re
import urllib.request
from pathlib import Path

html = urllib.request.urlopen("https://www.datagaffer.com/probability", timeout=20).read().decode("utf-8", "replace")
tabs = re.findall(r'prob-tab[^>]*>([^<]+)<', html)
print("tabs", tabs)
for term in ["joint", "grid", "homeGoals", "awayGoals", "scoreMatrix", "buildCorrect", "mostLikely"]:
    i = html.find(term)
    if i >= 0:
        print(term, html[i : i + 300].replace("\n", " ")[:250])

idx = html.find("prob-tab")
Path(__file__).parent.joinpath("prob_tabs_snippet.txt").write_text(html[idx : idx + 8000], encoding="utf-8")
