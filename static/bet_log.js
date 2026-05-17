(function () {
  const cfg = window.BET_LOG_CONFIG || {
    apiBase: "/api/bet-log",
    showSync: true,
    emptyBetsMsg: "No bets logged yet. Click Sync Recommended Bets.",
    scenarioTitle: "Scenario breakdown",
  };

  const syncBtn = document.getElementById("syncBtn");
  const autoResolveBtn = document.getElementById("autoResolveBtn");
  const statusEl = document.getElementById("status");
  const betRowsEl = document.getElementById("betRows");
  const overallKpisEl = document.getElementById("overallKpis");
  const scenarioStatsBodyEl = document.getElementById("scenarioStatsBody");
  const scenarioPanelMetaEl = document.getElementById("scenarioPanelMeta");
  const betsPanelMetaEl = document.getElementById("betsPanelMeta");

  let scenarioLookup = {};
  let dashboardCache = null;

  const IST_DATE_FORMATTER = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

  function td(text, className) {
    const el = document.createElement("td");
    el.textContent = text ?? "";
    if (className) el.className = className;
    return el;
  }

  function formatToIst(value) {
    if (!value) return "";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value;
    return IST_DATE_FORMATTER.format(d).replace(",", "");
  }

  function fmtOdds(val) {
    return val != null && val !== "" ? val : "—";
  }

  function fmtPnl(val) {
    const n = Number(val);
    if (Number.isNaN(n)) return "0";
    return n > 0 ? `+${n}` : String(n);
  }

  function pnlClass(val) {
    const n = Number(val);
    if (n > 0) return "pnl-pos";
    if (n < 0) return "pnl-neg";
    return "";
  }

  function scenarioParts(entry) {
    if (entry.scenario_category && entry.scenario_label) {
      return { category: entry.scenario_category, label: entry.scenario_label };
    }
    const s = scenarioLookup[entry.bet_type];
    if (s) return { category: s.category, label: s.label };
    return { category: "", label: entry.bet_type || "" };
  }

  function renderKpis(all) {
    const items = [
      { label: "Placed", value: all.placed },
      { label: "Won", value: all.won },
      { label: "Lost", value: all.lost },
      { label: "Win%", value: `${all.win_pct}%` },
      { label: "Avg odds", value: fmtOdds(all.avg_odds) },
      { label: "Unit PnL", value: fmtPnl(all.unit_pnl), cls: pnlClass(all.unit_pnl) },
    ];
    overallKpisEl.innerHTML = "";
    for (const item of items) {
      const card = document.createElement("div");
      card.className = "betlog-kpi";
      const lbl = document.createElement("span");
      lbl.className = "betlog-kpi-label";
      lbl.textContent = item.label;
      const val = document.createElement("span");
      val.className = "betlog-kpi-value" + (item.cls ? ` ${item.cls}` : "");
      val.textContent = item.value;
      card.appendChild(lbl);
      card.appendChild(val);
      overallKpisEl.appendChild(card);
    }
  }

  function flattenScenarios(dashboard) {
    const rows = [];
    for (const block of dashboard.by_category || []) {
      for (const s of block.scenarios || []) {
        rows.push({
          category: block.category,
          label: s.label || s.bet_type || "",
          bet_type: s.bet_type,
          placed: s.placed,
          won: s.won,
          lost: s.lost,
          win_pct: s.win_pct,
          avg_odds: s.avg_odds,
          unit_pnl: s.unit_pnl,
          hist_hit_pct: s.hist_hit_pct,
        });
      }
    }
    return rows;
  }

  function renderScenarioTable() {
    if (!dashboardCache) return;
    const rows = flattenScenarios(dashboardCache);

    scenarioStatsBodyEl.innerHTML = "";
    let lastCat = "";
    for (const s of rows) {
      const tr = document.createElement("tr");
      if (s.category !== lastCat) {
        tr.className = "stats-row-category-start";
        lastCat = s.category;
      }
      const catCell = td(s.category);
      catCell.className = "stats-category-cell";
      tr.appendChild(catCell);
      tr.appendChild(td(s.label));
      tr.appendChild(td(s.placed));
      tr.appendChild(td(s.won));
      tr.appendChild(td(s.lost));
      tr.appendChild(td(`${s.win_pct}%`));
      tr.appendChild(td(fmtOdds(s.avg_odds)));
      const pnlCell = td(fmtPnl(s.unit_pnl));
      pnlCell.className = pnlClass(s.unit_pnl);
      tr.appendChild(pnlCell);
      tr.appendChild(td(s.hist_hit_pct > 0 ? `${s.hist_hit_pct}%` : "—", "stats-hist"));
      scenarioStatsBodyEl.appendChild(tr);
    }

    if (!rows.length) {
      const tr = document.createElement("tr");
      const empty = td("No scenarios to display.");
      empty.colSpan = 9;
      empty.className = "stats-empty";
      tr.appendChild(empty);
      scenarioStatsBodyEl.appendChild(tr);
    }

    scenarioPanelMetaEl.textContent = `${rows.length} scenario${rows.length === 1 ? "" : "s"}`;
  }

  function drawDashboard(dashboard) {
    dashboardCache = dashboard;
    scenarioLookup = dashboard.by_scenario || dashboard.by_type || {};
    renderKpis(dashboard.all || {});
    renderScenarioTable();
  }

  function statusClass(status) {
    const s = (status || "open").toLowerCase();
    if (s === "won") return "status-won";
    if (s === "lost") return "status-lost";
    if (s === "push") return "status-push";
    return "status-open";
  }

  function renderRows(entries) {
    betRowsEl.innerHTML = "";
    betsPanelMetaEl.textContent = entries.length
      ? `${entries.length} bet${entries.length === 1 ? "" : "s"}`
      : "No bets";

    if (!entries.length) {
      const tr = document.createElement("tr");
      const empty = td(cfg.emptyBetsMsg);
      empty.colSpan = 11;
      empty.className = "stats-empty";
      tr.appendChild(empty);
      betRowsEl.appendChild(tr);
      return;
    }

    for (const e of entries) {
      const parts = scenarioParts(e);
      const tr = document.createElement("tr");
      tr.appendChild(td(formatToIst(e.fixture_date)));
      tr.appendChild(td(e.fixture || ""));
      tr.appendChild(td(e.league_name || ""));
      tr.appendChild(td(parts.category));
      tr.appendChild(td(parts.label));
      tr.appendChild(td(e.team_name || ""));
      tr.appendChild(td(e.odds ?? ""));
      tr.appendChild(td(e.units ?? 1));
      const statusCell = td(e.status || "open");
      statusCell.className = statusClass(e.status);
      tr.appendChild(statusCell);
      const pnlCell = td(e.pnl_units ?? "");
      pnlCell.className = pnlClass(e.pnl_units);
      tr.appendChild(pnlCell);

      const actions = document.createElement("td");
      actions.className = "resolve-actions";
      for (const [label, result] of [
        ["Won", "won"],
        ["Lost", "lost"],
        ["Push", "push"],
      ]) {
        const btn = document.createElement("button");
        btn.className = "small-btn";
        btn.textContent = label;
        btn.onclick = () => resolveBet(e.id, result);
        actions.appendChild(btn);
      }
      tr.appendChild(actions);
      betRowsEl.appendChild(tr);
    }

    if (window.TableTools) {
      window.TableTools.reapply(betRowsEl.closest("table"));
    }
  }

  function setStatus(msg, kind) {
    statusEl.textContent = msg;
    statusEl.className = "betlog-status" + (kind ? ` is-${kind}` : "");
  }

  async function resolveBet(id, result) {
    setStatus(`Resolving as ${result}...`);
    const res = await fetch(`${cfg.apiBase}/${id}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ result }),
    });
    const data = await res.json();
    drawDashboard(data.dashboard);
    renderRows(data.entries);
    setStatus(`Updated: ${result}`, "ok");
  }

  if (cfg.showSync && syncBtn) {
    syncBtn.addEventListener("click", async () => {
      setStatus("Syncing...");
      syncBtn.disabled = true;
      try {
        const res = await fetch(`${cfg.apiBase}/sync-recommended`, { method: "POST" });
        const data = await res.json();
        drawDashboard(data.dashboard);
        renderRows(data.entries);
          let msg = `Synced ${data.result.inserted} new bets`;
          if (data.result.updated_odds) {
            msg += `, updated ${data.result.updated_odds} odds`;
          }
          setStatus(msg, "ok");
      } catch (err) {
        setStatus("Sync failed", "error");
      } finally {
        syncBtn.disabled = false;
      }
    });
  }

  if (autoResolveBtn) {
    autoResolveBtn.addEventListener("click", async () => {
      setStatus("Auto resolving...");
      autoResolveBtn.disabled = true;
      try {
        const res = await fetch(`${cfg.apiBase}/auto-resolve`, { method: "POST" });
        const raw = await res.text();
        if (!res.ok) throw new Error(raw || `HTTP ${res.status}`);
        const data = JSON.parse(raw);
        if (data.result?.error) {
          setStatus(data.result.error, "error");
          return;
        }
        drawDashboard(data.dashboard);
        renderRows(data.entries);
        let msg = `Resolved ${data.result.resolved}/${data.result.open_checked}`;
        if (data.result.skipped_not_found) msg += ` (${data.result.skipped_not_found} not found)`;
        if (data.result.stopped_early) msg += " — run again for remainder";
        setStatus(msg, "ok");
      } catch (err) {
        setStatus(`Auto resolve failed: ${err.message || err}`, "error");
      } finally {
        autoResolveBtn.disabled = false;
      }
    });
  }

  function ensureTableTools(maxAttempts = 20) {
    let attempts = 0;
    const tick = () => {
      if (window.TableTools) {
        window.TableTools.enhanceAll();
        return;
      }
      attempts += 1;
      if (attempts < maxAttempts) setTimeout(tick, 150);
    };
    tick();
  }

  window.BetLogApp = {
    init(initialDashboard, initialEntries) {
      drawDashboard(initialDashboard);
      renderRows(initialEntries);
      ensureTableTools();
    },
  };
})();
