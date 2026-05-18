"""Extract JSON URLs and fixture data hints from a DataGaffer HTML page."""
from __future__ import annotations

import re
import sys
import urllib.request

FID = 1494170
path = sys.argv[1] if len(sys.argv) > 1 else f"/dashboard?fixture_id={FID}"
url = "https://www.datagaffer.com" + path
html = urllib.request.urlopen(url, timeout=20).read().decode("utf-8", "replace")
print("url", url, "bytes", len(html))
jsons = sorted(set(re.findall(r'["\']([/a-zA-Z0-9_\-./]+\.json[^"\']*)["\']', html)))
print("json refs:", jsons)
# inline JSON blobs
for pat in [r"fixture_id[\"']?\s*[:=]\s*(\d+)", r"correct[_-]?score", r"player[_-]?sim", r"heat[_-]?map", r"sim[_-]?card"]:
    hits = re.findall(pat, html, re.I)
    if hits:
        print(pat, "hits", len(hits), list(set(hits))[:5])
# script src
scripts = sorted(set(re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html)))
print("scripts:", scripts[:15])
