from __future__ import annotations

import urllib.request

html = urllib.request.urlopen("https://www.datagaffer.com/probability", timeout=20).read().decode("utf-8", "replace")
for term in ["matrix", "correct", "scoreline", "Score Matrix", "renderMatrix", "jointProb"]:
    if term.lower() in html.lower():
        idx = html.lower().find(term.lower())
        print(term, "found at", idx, html[idx : idx + 150].replace("\n", " "))
