(function () {
  "use strict";

  const IST_DATE_FORMATTER = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

  function el(id) {
    return document.getElementById(id);
  }

  function formatScrapedAt(value) {
    if (!value || value === "Never") return value || "Never";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value;
    return IST_DATE_FORMATTER.format(d).replace(",", "");
  }

  function fmtPct(v) {
    if (v == null || v === "") return "—";
    return `${Number(v).toFixed(1)}%`;
  }

  function logoImg(logo, name, className) {
    if (logo) {
      const img = document.createElement("img");
      img.src = logo;
      img.alt = name || "";
      img.className = className;
      img.loading = "lazy";
      img.onerror = function () {
        const ph = initialsPlaceholder(name, className);
        img.replaceWith(ph);
      };
      return img;
    }
    return initialsPlaceholder(name, className);
  }

  function initialsPlaceholder(name, className) {
    const div = document.createElement("div");
    div.className = `${className} slate-card__logo--placeholder`;
    const parts = (name || "?").trim().split(/\s+/);
    div.textContent = (parts[0][0] || "?") + (parts[1]?.[0] || "");
    return div;
  }

  function renderSlateCarousel(slate) {
    const root = el("slateCarousel");
    if (!root) return;
    root.innerHTML = "";

    if (!slate.length) {
      const empty = document.createElement("p");
      empty.className = "slate-empty";
      empty.textContent =
        "No fixtures for today. Click Refresh from DataGaffer to load the latest slate.";
      root.appendChild(empty);
      return;
    }

    for (const fx of slate) {
      const link = document.createElement("a");
      link.className = "slate-card-link";
      link.href = fx.fixture_id ? `/fixture/${fx.fixture_id}` : "#";

      const card = document.createElement("article");
      card.className = "slate-card";

      const time = document.createElement("div");
      time.className = "slate-card__time";
      time.textContent = fx.kickoff || "—";
      card.appendChild(time);

      const teams = document.createElement("div");
      teams.className = "slate-card__teams";

      const home = document.createElement("div");
      home.className = "slate-card__team";
      home.appendChild(logoImg(fx.home_logo, fx.home_team, "slate-card__logo"));
      const homePct = document.createElement("div");
      homePct.className = "slate-card__pct";
      homePct.textContent = fmtPct(fx.win_pct);
      const homeName = document.createElement("div");
      homeName.className = "slate-card__name";
      homeName.textContent = fx.home_team || "";
      home.appendChild(homePct);
      home.appendChild(homeName);

      const away = document.createElement("div");
      away.className = "slate-card__team";
      away.appendChild(logoImg(fx.away_logo, fx.away_team, "slate-card__logo"));
      const awayPct = document.createElement("div");
      awayPct.className = "slate-card__pct";
      awayPct.textContent = fmtPct(fx.away_win_pct);
      const awayName = document.createElement("div");
      awayName.className = "slate-card__name";
      awayName.textContent = fx.away_team || "";
      away.appendChild(awayPct);
      away.appendChild(awayName);

      teams.appendChild(home);
      teams.appendChild(away);
      card.appendChild(teams);

      if (fx.league_name) {
        const league = document.createElement("div");
        league.className = "slate-card__league";
        league.textContent = fx.league_name;
        card.appendChild(league);
      }

      link.appendChild(card);
      root.appendChild(link);
    }
  }

  function renderHome(slate) {
    renderSlateCarousel(slate);
  }

  function wireRefresh() {
    const btn = el("refreshBtn");
    const status = el("status");
    if (!btn) return;

    btn.addEventListener("click", async () => {
      status.textContent = "Refreshing...";
      btn.disabled = true;
      try {
        const res = await fetch("/api/refresh", { method: "POST" });
        const data = await res.json();
        if (!data.success) {
          status.textContent = `Failed: ${data.message}`;
          return;
        }
        const slateRes = await fetch("/api/slate");
        const slateData = await slateRes.json();
        const scrapedAtEl = el("scrapedAt");
        if (scrapedAtEl) scrapedAtEl.textContent = formatScrapedAt(slateData.scraped_at);
        renderHome(slateData.slate || []);
        status.textContent = "Done";
      } catch {
        status.textContent = "Failed: network error";
      } finally {
        btn.disabled = false;
      }
    });
  }

  window.HomeApp = {
    init(slate) {
      const scrapedAtEl = el("scrapedAt");
      if (scrapedAtEl) scrapedAtEl.textContent = formatScrapedAt(scrapedAtEl.textContent.trim());
      renderHome(slate || []);
      wireRefresh();
    },
  };
})();
