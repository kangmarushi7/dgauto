from __future__ import annotations

import urllib.request
from pathlib import Path

html = urllib.request.urlopen("https://www.datagaffer.com/goal_zone", timeout=20).read().decode("utf-8", "replace")
idx = html.find("poissonPMF")
Path(__file__).parent.joinpath("poisson_snippet.txt").write_text(html[idx : idx + 4000], encoding="utf-8")
print("written", idx)
