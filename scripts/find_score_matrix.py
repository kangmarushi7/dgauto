from __future__ import annotations

import json
import re
import urllib.request


def find_keys(obj, path: str = "") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if any(x in k.lower() for x in ["matrix", "grid", "correct", "scoreline", "score_prob"]):
                print("KEY", p, type(v).__name__, str(v)[:80])
            find_keys(v, p)
    elif isinstance(obj, list) and obj:
        find_keys(obj[0], path + "[]")


def main() -> None:
    fx = json.load(urllib.request.urlopen("https://www.datagaffer.com/fixtures.json", timeout=15))
    find_keys(fx[0])
    html = urllib.request.urlopen("https://www.datagaffer.com/probability", timeout=15).read().decode()
    print("prob jsons", sorted(set(re.findall(r'["\']([/a-zA-Z0-9_./-]+\.json)["\']', html))))


if __name__ == "__main__":
    main()
