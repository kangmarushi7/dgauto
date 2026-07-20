"""Probe Sports Reference page structure for scraper debugging."""
from playwright.sync_api import sync_playwright

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def probe(url: str) -> None:
    print("===", url)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=UA)
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(2500)
        before = page.evaluate(
            """() => ({
              title: document.title,
              tables: Array.from(document.querySelectorAll('table')).map(t => ({
                id: t.id, rows: t.tBodies?.[0]?.rows?.length || 0
              })),
              hasPlayers: !!document.querySelector('#players_standard_batting'),
              textSample: document.body.innerText.slice(0, 200)
            })"""
        )
        print("BEFORE", before)

        # Uncomment like production
        page.evaluate(
            """() => {
          const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_COMMENT);
          const nodes = [];
          let node;
          while ((node = walker.nextNode())) nodes.push(node);
          for (const c of nodes) {
            const wrap = document.createElement('div');
            wrap.innerHTML = c.nodeValue || '';
            c.parentNode && c.parentNode.insertBefore(wrap, c);
          }
        }"""
        )
        after = page.evaluate(
            """() => {
          const table = document.querySelector('#players_standard_batting')
            || document.querySelector('#players_standard_pitching')
            || document.querySelector('#per_minute_stats')
            || document.querySelector('table.stats_table');
          let sample = [];
          if (table) {
            sample = Array.from(table.querySelectorAll('tbody tr')).slice(0, 3).map(tr => {
              const a = tr.querySelector('[data-stat="player"] a, td a');
              return a ? a.textContent.trim() : tr.textContent.trim().slice(0, 60);
            });
          }
          return {
            tables: Array.from(document.querySelectorAll('table')).map(t => ({
              id: t.id, rows: t.tBodies?.[0]?.rows?.length || 0
            })).filter(t => t.rows > 0).slice(0, 8),
            hasPlayers: !!document.querySelector('#players_standard_batting'),
            sample
          };
        }"""
        )
        print("AFTER", after)
        browser.close()


if __name__ == "__main__":
    for y in (2025, 2026, 2024):
        probe(f"https://www.baseball-reference.com/leagues/majors/{y}-standard-batting.html")
    probe("https://www.basketball-reference.com/leagues/NBA_2026_per_minute.html")
