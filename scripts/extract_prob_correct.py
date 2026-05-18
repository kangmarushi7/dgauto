from __future__ import annotations

import urllib.request
from pathlib import Path

html = urllib.request.urlopen("https://www.datagaffer.com/probability", timeout=20).read().decode("utf-8", "replace")
idx = html.lower().find("correct score")
if idx < 0:
    idx = html.lower().find("correctscore")
if idx < 0:
    idx = html.lower().find("score matrix")
Path(__file__).parent.joinpath("prob_correct_snippet.txt").write_text(
    html[max(0, idx - 500) : idx + 5000], encoding="utf-8"
)
print("idx", idx)
