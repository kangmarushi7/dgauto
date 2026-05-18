from __future__ import annotations

import re
import urllib.request

FID = 1494170
html = urllib.request.urlopen(
    f"https://www.datagaffer.com/goal_zone?fixture_id={FID}", timeout=20
).read().decode("utf-8", "replace")
for pat in [
    r"correct[_-]?score[^\"']{0,40}",
    r"score[_-]?matrix[^\"']{0,40}",
    r"scoreline[^\"']{0,40}",
    r"poisson[^\"']{0,40}",
    r"grid[^\"']{0,30}",
]:
    hits = re.findall(pat, html, re.I)
    if hits:
        print(pat, sorted(set(hits))[:10])
