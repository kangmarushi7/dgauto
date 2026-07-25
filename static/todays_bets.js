(function () {
  "use strict";

  const root = document.getElementById("betsRoot");
  const strategyFilter = document.getElementById("strategyFilter");
  const kpiOpen = document.getElementById("kpiOpen");
  const kpiPending = document.getElementById("kpiPending");
  const kpiStake = document.getElementById("kpiStake");
  const resyncBtn = document.getElementById("resyncToday");
  const resyncStatus = document.getElementById("resyncStatus");

  let state = window.INITIAL_TODAYS_BETS || { entries: [], strategies: [] };

  function fmtInr(n) {
    const v = Number(n || 0);
    return `${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}₹`;
  }

  function fmtOdds(v) {
    if (v == null || v === "") return "—";
    return Number(v).toFixed(2);
  }

  function fmtEv(v) {
    if (v == null || v === "") return "—";
    const n = Number(v);
    const cls = n > 0 ? "bets-pos" : n < 0 ? "bets-neg" : "";
    return `<span class="mono ${cls}">${n > 0 ? "+" : ""}${n.toFixed(1)}%</span>`;
  }

  function statusPill(status) {
    const s = String(status || "pending").toLowerCase();
    const label = s === "open" ? "Open" : s === "settled" ? "Settled" : "Pending";
    return `<span class="bets-pill bets-pill--${s}">${label}</span>`;
  }

  function fillStrategies() {
    const opts = state.strategies || [];
    for (const s of opts) {
      const o = document.createElement("option");
      o.value = s.id;
      o.textContent = s.short || s.label;
      strategyFilter.appendChild(o);
    }
  }

  function renderKpis() {
    kpiOpen.textContent = String(state.open || 0);
    kpiPending.textContent = String(state.pending || 0);
    kpiStake.textContent = fmtInr(state.open_stake_inr || 0);
  }

  function render() {
    const rows = state.entries || [];
    renderKpis();
    if (!rows.length) {
      root.innerHTML = `
        <div class="bets-empty bets-table-wrap">
          <h2>No bets placed yet today</h2>
          <p>Sync a strategy log or wait for auto-sync — qualified picks will show up here.</p>
        </div>`;
      return;
    }

    const body = rows
      .map(
        (b) => `
      <tr>
        <td class="mono">${b.time_label || "—"}</td>
        <td>
          <div class="bets-fixture">
            <span class="bets-fixture__name">${escapeHtml(b.fixture || "—")}</span>
            <span class="bets-fixture__league">${escapeHtml(b.league || "")}</span>
          </div>
        </td>
        <td>${escapeHtml(b.strategy_short || b.strategy_label || "")}</td>
        <td>${escapeHtml(b.market || "—")}</td>
        <td class="mono">${fmtInr(b.stake_inr)}</td>
        <td class="mono">${fmtOdds(b.odds)}</td>
        <td>${fmtEv(b.ev)}</td>
        <td>${statusPill(b.status)}</td>
      </tr>`
      )
      .join("");

    root.innerHTML = `
      <div class="bets-table-wrap">
        <table class="bets-table" data-column-filters="1">
          <thead>
            <tr>
              <th scope="col">Time</th>
              <th scope="col">Fixture</th>
              <th scope="col">Strategy</th>
              <th scope="col">Market</th>
              <th scope="col">Stake</th>
              <th scope="col">Odds</th>
              <th scope="col">EV%</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>`;
    if (window.TableTools) {
      window.TableTools.enhanceTable(root.querySelector("table"));
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function reload() {
    const strategy = strategyFilter.value;
    const qs = strategy ? `?strategy=${encodeURIComponent(strategy)}` : "";
    const res = await fetch(`/api/bets/today${qs}`);
    state = await res.json();
    render();
  }

  function summarizeResync(resync) {
    if (!resync || typeof resync !== "object") return "";
    const deleted = Number(resync.deleted_total || 0);
    const inserted = Number(resync.inserted_total || 0);
    const failed = Object.keys(resync)
      .filter((k) => resync[k] && typeof resync[k] === "object" && resync[k].ok === false)
      .map((k) => k.toUpperCase());
    let msg = `Replaced ${deleted}, added ${inserted}.`;
    if (failed.length) msg += ` Issues: ${failed.join(", ")}.`;
    return msg;
  }

  async function resyncToday() {
    if (!resyncBtn) return;
    const original = resyncBtn.textContent;
    resyncBtn.disabled = true;
    resyncBtn.textContent = "Resyncing…";
    if (resyncStatus) resyncStatus.textContent = "";
    try {
      const strategy = strategyFilter.value;
      const qs = strategy ? `?strategy=${encodeURIComponent(strategy)}` : "";
      const res = await fetch(`/api/bets/resync-today${qs}`, { method: "POST" });
      const data = await res.json();
      if (!res.ok || data.success === false) {
        throw new Error(data.error || "Resync failed");
      }
      state = data;
      render();
      if (resyncStatus) resyncStatus.textContent = summarizeResync(data.resync);
    } catch (err) {
      if (resyncStatus) resyncStatus.textContent = `Failed: ${err.message || err}`;
    } finally {
      resyncBtn.disabled = false;
      resyncBtn.textContent = original;
    }
  }

  fillStrategies();
  render();
  strategyFilter.addEventListener("change", () => {
    reload().catch(() => {
      root.innerHTML = `<div class="bets-empty"><p>Failed to load bets.</p></div>`;
    });
  });
  if (resyncBtn) {
    resyncBtn.addEventListener("click", () => {
      resyncToday();
    });
  }
})();
