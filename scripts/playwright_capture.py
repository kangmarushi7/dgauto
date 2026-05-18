"""Capture JSON network responses from DataGaffer pages (optional login via .env)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

FID = int(sys.argv[1]) if len(sys.argv) > 1 else 1494170

URLS = [
    f"https://www.datagaffer.com/dashboard?fixture_id={FID}",
    f"https://www.datagaffer.com/goal_zone?fixture_id={FID}",
    "https://www.datagaffer.com/sim_cards",
    "https://www.datagaffer.com/heat_maps",
    "https://www.datagaffer.com/player_simulations",
    "https://www.datagaffer.com/parlay_builder",
    "https://www.datagaffer.com/projections",
    "https://www.datagaffer.com/probability",
    "https://www.datagaffer.com/trends",
]


def main() -> None:
    from playwright.sync_api import sync_playwright

    email = os.getenv("DG_EMAIL", "")
    password = os.getenv("DG_PASSWORD", "")
    captured: dict[str, list] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        def on_response(resp):
            url = resp.url
            if ".json" in url and "datagaffer.com" in url:
                try:
                    body = resp.json()
                except Exception:
                    return
                captured.setdefault(url, []).append(body)

        page.on("response", on_response)

        if email and password:
            page.goto("https://www.datagaffer.com/login", wait_until="networkidle", timeout=60000)
            page.fill("input[type='email']", email)
            page.fill("input[type='password']", password)
            page.click("button[type='submit']")
            page.wait_for_timeout(3000)

        for url in URLS:
            print("visit", url)
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(2000)
            except Exception as e:
                print("  fail", e)

        browser.close()

    print("\n=== captured JSON URLs ===")
    for url, bodies in sorted(captured.items()):
        sample = bodies[0]
        kind = type(sample).__name__
        extra = len(sample) if isinstance(sample, (list, dict)) else ""
        print(url, kind, extra)

    out = Path(__file__).parent / "captured_network.json"
    # trim huge payloads
    slim = {u: (b[0] if len(str(b[0])) < 5000 else str(type(b[0]))) for u, b in captured.items()}
    out.write_text(json.dumps(slim, indent=2)[:50000], encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
