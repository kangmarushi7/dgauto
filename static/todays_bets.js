(function () {
  "use strict";

  const root = document.getElementById("betsRoot");
  const strategyFilter = document.getElementById("strategyFilter");
  const kpiOpen = document.getElementById("kpiOpen");
  const kpiPending = document.getElementById("kpiPending");
  const kpiStake = document.getElementById("kpiStake");

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
        <table class="bets-table">
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

  fillStrategies();
  render();
  strategyFilter.addEventListener("change", () => {
    reload().catch(() => {
      root.innerHTML = `<div class="bets-empty"><p>Failed to load bets.</p></div>`;
    });
  });
})();
