(function () {
  "use strict";

  const cfg = window.BET_LOG_CONFIG || {
    apiBase: "/api/bet-log",
    showSync: true,
    emptyBetsMsg: "No bets logged yet. Sync recommended bets from Home.",
  };

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

  const IST_PART_FORMATTER = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    hourCycle: "h23",
    hour12: false,
  });

  function el(id) {
    return document.getElementById(id);
  }

  function td(text, className) {
    const cell = document.createElement("td");
    cell.textContent = text ?? "";
    if (className) cell.className = className;
    return cell;
  }

  function formatToIst(value) {
    if (!value) return "";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value;
    return IST_DATE_FORMATTER.format(d).replace(",", "");
  }

  function istParts(value) {
    const d = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(d.getTime())) return null;
    const parts = Object.fromEntries(
      IST_PART_FORMATTER.formatToParts(d).map((p) => [p.type, p.value]),
    );
    return {
      dayKey: `${parts.year}-${parts.month}-${parts.day}`,
      hour: Number(parts.hour || 0),
    };
  }

  function tomorrowKeyFromIstDay(dayKey) {
    const [year, month, day] = dayKey.split("-").map(Number);
    const utcNoon = new Date(Date.UTC(year, month - 1, day + 1, 12, 0, 0));
    return istParts(utcNoon)?.dayKey;
  }

  /** Today's Bets window: noon IST today through 09:00 IST tomorrow. */
  const TODAYS_BETS_START_HOUR = 12;
  const TODAYS_BETS_END_HOUR = 9;

  function isTodayFixture(entry) {
    const fixture = istParts(entry.fixture_date);
    if (!fixture) return false;
    const today = istParts(new Date());
    if (!today) return false;
    if (fixture.dayKey === today.dayKey) {
      return fixture.hour >= TODAYS_BETS_START_HOUR;
    }
    return (
      fixture.dayKey === tomorrowKeyFromIstDay(today.dayKey) &&
      fixture.hour < TODAYS_BETS_END_HOUR
    );
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
    const overallKpisEl = el("overallKpis");
    if (!overallKpisEl) return;

    const items = [
      { label: "Placed", value: all.placed ?? 0 },
      { label: "Won", value: all.won ?? 0 },
      { label: "Lost", value: all.lost ?? 0 },
      { label: "Win%", value: `${all.win_pct ?? 0}%` },
      { label: "Avg odds", value: fmtOdds(all.avg_odds) },
      { label: "Unit PnL", value: fmtPnl(all.unit_pnl), cls: pnlClass(all.unit_pnl) },
    ];
    overallKpisEl.innerHTML = "";
    for (const item of items) {
      const card = document.createElement('div');
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
    const scenarioStatsBodyEl = el("scenarioStatsBody");
    const scenarioPanelMetaEl = el("scenarioPanelMeta");
    if (!scenarioStatsBodyEl || !dashboardCache) return;

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

    if (scenarioPanelMetaEl) {
      scenarioPanelMetaEl.textContent = `${rows.length} scenario${rows.length === 1 ? "" : "s"}`;
    }
  }

  function drawDashboard(dashboard) {
    dashboardCache = dashboard || {};
    scenarioLookup = dashboardCache.by_scenario || dashboardCache.by_type || {};
    renderKpis(dashboardCache.all || {});
    renderScenarioTable();
  }

  function statusClass(status) {
    const s = (status || "open").toLowerCase();
    if (s === "won") return "status-won";
    if (s === "lost") return "status-lost";
    if (s === "push") return "status-push";
    return "status-open";
  }

  function buildBetRow(e) {
    const parts = scenarioParts(e);
    const tr = document.createElement("tr");
    const dateCell = td(formatToIst(e.fixture_date));
    const fixtureCell = td(e.fixture || "");
    const teamCell = td(e.team_name || "");
    const betCell = td(parts.label);
    const leagueCell = td(e.league_name || "");
    const categoryCell = td(parts.category);
    for (const cell of [fixtureCell, teamCell, betCell, leagueCell, categoryCell]) {
      if (cell.textContent) cell.title = cell.textContent;
    }
    tr.appendChild(dateCell);
    tr.appendChild(fixtureCell);
    tr.appendChild(teamCell);
    tr.appendChild(betCell);
    tr.appendChild(td(e.odds ?? ""));
    const statusCell = td(e.status || "open");
    statusCell.className = statusClass(e.status);
    tr.appendChild(statusCell);

    const actions = document.createElement("td");
    actions.className = "resolve-actions col-resolve";
    const status = (e.status || "open").toLowerCase();
    if (status === "open") {
      for (const [label, result] of [
        ["Won", "won"],
        ["Lost", "lost"],
        ["Push", "push"],
      ]) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `betlog-resolve-btn betlog-resolve-btn--${result}`;
        btn.textContent = label;
        btn.onclick = () => resolveBet(e.id, result);
        actions.appendChild(btn);
      }
    } else {
      const settled = document.createElement("span");
      settled.className = "resolve-settled";
      settled.textContent = "Settled";
      actions.appendChild(settled);
    }
    tr.appendChild(actions);
    tr.appendChild(leagueCell);
    tr.appendChild(categoryCell);
    tr.appendChild(td(e.units ?? 1));
    const pnlCell = td(
      e.status && e.status !== "open" ? fmtPnl(e.pnl_units) : "—",
    );
    pnlCell.className = pnlClass(e.pnl_units);
    tr.appendChild(pnlCell);
    return tr;
  }

  function renderBetTable(bodyEl, metaEl, entries, emptyMsg) {
    if (!bodyEl) return;

    const list = entries || [];
    bodyEl.innerHTML = "";
    if (metaEl) {
      metaEl.textContent = list.length
        ? `${list.length} bet${list.length === 1 ? "" : "s"}`
        : "No bets";
    }

    if (!list.length) {
      const tr = document.createElement("tr");
      const empty = td(emptyMsg);
      empty.colSpan = 11;
      empty.className = "stats-empty";
      tr.appendChild(empty);
      bodyEl.appendChild(tr);
      return;
    }

    for (const e of list) {
      bodyEl.appendChild(buildBetRow(e));
    }

    if (window.TableTools) {
      window.TableTools.reapply(bodyEl.closest("table"));
    }
  }

  function renderTodayRows(entries) {
    const todayBetRowsEl = el("todayBetRows");
    const todayBetsPanelMetaEl = el("todayBetsPanelMeta");
    const todays = (entries || [])
      .filter(isTodayFixture)
      .sort((a, b) => new Date(a.fixture_date || 0) - new Date(b.fixture_date || 0));
    renderBetTable(
      todayBetRowsEl,
      todayBetsPanelMetaEl,
      todays,
      "No bets for today's fixture window. Sync recommended bets after refreshing the slate.",
    );
  }

  function renderRows(entries) {
    renderTodayRows(entries);
    renderBetTable(el("betRows"), el("betsPanelMeta"), entries || [], cfg.emptyBetsMsg);
  }

  function setStatus(msg, kind) {
    const statusEl = el("status");
    if (!statusEl) return;
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

  function wireActions() {
    const syncBtn = el("syncBtn");
    const autoResolveBtn = el("autoResolveBtn");

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
          if (data.result.updated_odds) msg += `, updated ${data.result.updated_odds} odds`;
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
  }

  window.BetLogApp = {
    init(initialDashboard, initialEntries) {
      drawDashboard(initialDashboard || {});
      renderRows(initialEntries || []);
      ensureTableTools();
    },
  };

  wireActions();
})();
