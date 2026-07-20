"""Inspect ESPN MLB stats DOM for scraper selectors."""
from playwright.sync_api import sync_playwright
import json

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

url = "https://www.espn.com/mlb/stats/player/_/table/batting/sort/avg/dir/desc"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent=UA, viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    try:
        page.wait_for_selector("table tbody tr", timeout=20000)
    except Exception as e:
        print("wait err", e)
    page.wait_for_timeout(2000)
    info = page.evaluate(
        """() => {
      const tables = Array.from(document.querySelectorAll('table'));
      return {
        count: tables.length,
        tables: tables.map((t, idx) => {
          const headers = Array.from(t.querySelectorAll('thead th, thead td, tr:first-child th, tr:first-child td')).map(h => h.textContent.trim());
          const rows = Array.from(t.querySelectorAll('tbody tr')).slice(0, 2).map(tr =>
            Array.from(tr.querySelectorAll('td, th')).map(c => ({
              text: c.textContent.trim(),
              html: c.innerHTML.slice(0, 120)
            }))
          );
          return { idx, headers, rowCount: t.querySelectorAll('tbody tr').length, rows, cls: t.className };
        })
      };
    }"""
    )
    print(json.dumps(info, indent=2)[:6000])
    browser.close()
