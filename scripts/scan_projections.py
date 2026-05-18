from __future__ import annotations

import re
import urllib.request

html = urllib.request.urlopen("https://www.datagaffer.com/projections", timeout=20).read().decode("utf-8", "replace")
print("bytes", len(html))
jsons = sorted(set(re.findall(r'["\']([/a-zA-Z0-9_\-./]+\.json)["\']', html)))
print("jsons", jsons)
for kw in ["correct", "score", "matrix", "distribution", "prob_grid"]:
    if kw in html.lower():
        print("has", kw)
