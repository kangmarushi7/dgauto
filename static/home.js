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

  function fmtNum(v, d = 2) {
    if (v == null || v === "") return "—";
    return Number(v).toFixed(d);
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

  function pickChip(pick) {
    const chip = document.createElement("span");
    const tone = pick.tone || "none";
    chip.className = `pick-chip pick-chip--${tone}`;
    chip.textContent = pick.label;
    if (pick.detail) {
      const small = document.createElement("small");
      small.textContent = pick.detail;
      chip.appendChild(document.createElement("br"));
      chip.appendChild(small);
    }
    return chip;
  }

  function renderFixtureAnalysis(slate) {
    const root = el("fixtureAnalysis");
    if (!root) return;
    root.innerHTML = "";

    if (!slate.length) return;

    for (const fx of slate) {
      const panel = document.createElement("article");
      panel.className = `fixture-panel signal-${fx.signal || "watch"}`;

      const panelLink = document.createElement("a");
      panelLink.className = "fixture-panel-link";
      panelLink.href = fx.fixture_id ? `/fixture/${fx.fixture_id}` : "#";
      panelLink.textContent = "Full analysis →";

      const head = document.createElement("header");
      head.className = "fixture-panel__head";

      const logos = document.createElement("div");
      logos.className = "fixture-panel__logos";
      logos.appendChild(logoImg(fx.home_logo, fx.home_team, ""));
      const vs = document.createElement("span");
      vs.className = "fixture-panel__vs";
      vs.textContent = "vs";
      logos.appendChild(vs);
      logos.appendChild(logoImg(fx.away_logo, fx.away_team, ""));

      const title = document.createElement("div");
      title.className = "fixture-panel__title";
      const h3 = document.createElement("h3");
      h3.textContent = fx.fixture || `${fx.home_team} vs ${fx.away_team}`;
      const meta = document.createElement("p");
      meta.className = "fixture-panel__meta";
      meta.textContent = [fx.league_name, fx.kickoff].filter(Boolean).join(" · ");
      title.appendChild(h3);
      title.appendChild(meta);

      head.appendChild(logos);
      head.appendChild(title);
      panel.appendChild(head);

      const body = document.createElement("div");
      body.className = "fixture-panel__body";

      const winGrid = document.createElement("div");
      winGrid.className = "stat-grid";
      for (const [label, val] of [
        ["Home", fmtPct(fx.win_pct)],
        ["Draw", fmtPct(fx.draw_pct)],
        ["Away", fmtPct(fx.away_win_pct)],
      ]) {
        const cell = document.createElement("div");
        cell.className = "stat-cell";
        const lbl = document.createElement("span");
        lbl.className = "stat-cell__label";
        lbl.textContent = label;
        const v = document.createElement("span");
        v.className = "stat-cell__value";
        v.textContent = val;
        cell.appendChild(lbl);
        cell.appendChild(v);
        winGrid.appendChild(cell);
      }
      body.appendChild(winGrid);

      const xgRow = document.createElement("div");
      xgRow.className = "stat-row";
      xgRow.innerHTML = `<span>Proj xG</span><strong>${fmtNum(fx.home_projected_goals)} / ${fmtNum(fx.away_projected_goals)} (total ${fmtNum(fx.projected_total_goals)})</strong>`;
      body.appendChild(xgRow);

      const marketRow = document.createElement("div");
      marketRow.className = "stat-row";
      marketRow.innerHTML = `<span>Markets</span><strong>O1.5 ${fmtPct(fx.over_1_5_pct)} · O2.5 ${fmtPct(fx.over_25_pct)} · BTTS ${fmtPct(fx.btts_pct)}</strong>`;
      body.appendChild(marketRow);

      const oddsRow = document.createElement("div");
      oddsRow.className = "stat-row";
      const oddsParts = [];
      if (fx.home_ml_odds) oddsParts.push(`H ${fx.home_ml_odds}`);
      if (fx.away_ml_odds) oddsParts.push(`A ${fx.away_ml_odds}`);
      if (fx.over_1_5_odds) oddsParts.push(`O1.5 @${fx.over_1_5_odds}`);
      if (fx.btts_yes_odds) oddsParts.push(`BTTS @${fx.btts_yes_odds}`);
      oddsRow.innerHTML = `<span>Book</span><strong>${oddsParts.length ? oddsParts.join(" · ") : "—"}</strong>`;
      body.appendChild(oddsRow);

      const picks = document.createElement("div");
      picks.className = "fixture-picks";
      if (fx.picks && fx.picks.length) {
        for (const p of fx.picks) picks.appendChild(pickChip(p));
      } else {
        const none = document.createElement("span");
        none.className = "pick-chip pick-chip--none";
        none.textContent = "No strong picks on current rules";
        picks.appendChild(none);
      }
      body.appendChild(picks);

      const foot = document.createElement("footer");
      foot.className = "fixture-panel__foot";
      foot.appendChild(panelLink);
      panel.appendChild(body);
      panel.appendChild(foot);
      root.appendChild(panel);
    }
  }

  function renderHome(slate) {
    renderSlateCarousel(slate);
    renderFixtureAnalysis(slate);
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
