"""Probe alternate MLB stats sources."""
from playwright.sync_api import sync_playwright

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

URLS = [
    "https://www.espn.com/mlb/stats/player/_/table/batting/sort/avg/dir/desc",
    "https://www.espn.com/mlb/stats/player/_/view/pitching/table/pitching/sort/ERA/dir/asc",
    "https://www.fangraphs.com/leaders/major-league?pos=all&stats=bat&lg=all&qual=y&type=8&season=2025&month=0&season1=2025",
    "https://baseballsavant.mlb.com/leaderboard/expected_statistics?type=batter&year=2025&position=&team=&min=q",
    "https://www.mlb.com/stats/",
]


def probe(url: str) -> None:
    print("===", url[:90])
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(4000)
            info = page.evaluate(
                """() => {
              const tables = Array.from(document.querySelectorAll('table')).map(t => ({
                cls: (t.className||'').toString().slice(0,60),
                rows: t.querySelectorAll('tbody tr').length || t.querySelectorAll('tr').length
              }));
              return {
                title: document.title.slice(0,80),
                tables: tables.filter(t => t.rows > 0).slice(0,6),
                sample: document.body.innerText.slice(0, 180).replace(/\\s+/g,' ')
              };
            }"""
            )
            print(info)
        except Exception as e:
            print("ERR", e)
        finally:
            browser.close()


if __name__ == "__main__":
    for u in URLS:
        probe(u)
