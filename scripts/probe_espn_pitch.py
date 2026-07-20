"""Inspect ESPN pitching table headers."""
from playwright.sync_api import sync_playwright
import json

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
url = "https://www.espn.com/mlb/stats/player/_/view/pitching/table/pitching/sort/ERA/dir/asc"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent=UA, viewport={"width": 1440, "height": 900})
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_selector("table tbody tr", timeout=20000)
    info = page.evaluate(
        """() => {
      const tables = Array.from(document.querySelectorAll('table'));
      const nameRows = Array.from(tables[0].querySelectorAll('tbody tr')).slice(0,2).map(tr => ({
        text: tr.textContent.trim(),
        a: tr.querySelector('a')?.textContent?.trim(),
        spans: Array.from(tr.querySelectorAll('span')).map(s => s.textContent.trim())
      }));
      const headers = Array.from(tables[1].querySelectorAll('thead th')).map(h => h.textContent.trim());
      const stats = Array.from(tables[1].querySelectorAll('tbody tr')).slice(0,1).map(tr =>
        Array.from(tr.querySelectorAll('td')).map(td => td.textContent.trim())
      );
      return { nameRows, headers, stats };
    }"""
    )
    print(json.dumps(info, indent=2))
    browser.close()
