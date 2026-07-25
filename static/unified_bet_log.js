(function () {
  "use strict";

  const root = document.getElementById("betsRoot");
  const rangePill = document.getElementById("rangePill");
  const strategyFilter = document.getElementById("strategyFilter");
  const resultFilter = document.getElementById("resultFilter");
  const daysFilter = document.getElementById("daysFilter");
  const pager = document.getElementById("pager");
  const pagerMeta = document.getElementById("pagerMeta");
  const prevPage = document.getElementById("prevPage");
  const nextPage = document.getElementById("nextPage");

  let state = window.INITIAL_BET_LOG || { entries: [], strategies: [], page: 1, pages: 1 };
  let sortKey = "time";
  let sortDir = "desc";

  function fmtInr(n) {
    const v = Number(n || 0);
    const sign = v > 0 ? "+" : "";
    return `${sign}${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}₹`;
  }

  function fmtOdds(v) {
    if (v == null || v === "") return "—";
    return Number(v).toFixed(2);
  }

  function resultPill(result) {
    const r = String(result || "").toLowerCase();
    const label = r === "won" ? "Win" : r === "lost" ? "Loss" : "Push";
    return `<span class="bets-pill bets-pill--${r}">${label}</span>`;
  }

  function pnlCell(v) {
    if (v == null) return "—";
    const n = Number(v);
    const cls = n > 0 ? "bets-pos" : n < 0 ? "bets-neg" : "";
    return `<span class="mono ${cls}">${fmtInr(n)}</span>`;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fillStrategies() {
    for (const s of state.strategies || []) {
      const o = document.createElement("option");
      o.value = s.id;
      o.textContent = s.short || s.label;
      strategyFilter.appendChild(o);
    }
  }

  function sortedRows() {
    const rows = [...(state.entries || [])];
    rows.sort((a, b) => {
      let av = a[sortKey];
      let bv = b[sortKey];
      if (sortKey === "pnl_inr" || sortKey === "stake_inr" || sortKey === "odds") {
        av = Number(av || 0);
        bv = Number(bv || 0);
      } else {
        av = String(av || "");
        bv = String(bv || "");
      }
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
    return rows;
  }

  function renderPill() {
    rangePill.textContent = state.range_label || "";
    const net = Number(state.net_pnl_inr || 0);
    rangePill.classList.toggle("is-pos", net > 0);
    rangePill.classList.toggle("is-neg", net < 0);
  }

  function renderPager() {
    const total = state.total || 0;
    const page = state.page || 1;
    const pages = state.pages || 1;
    if (total <= (state.page_size || 50)) {
      pager.hidden = true;
      return;
    }
    pager.hidden = false;
    pagerMeta.textContent = `Page ${page} / ${pages} · ${total} bets`;
    prevPage.disabled = page <= 1;
    nextPage.disabled = page >= pages;
  }

  function render() {
    renderPill();
    renderPager();
    const rows = sortedRows();
    if (!rows.length) {
      root.innerHTML = `
        <div class="bets-empty bets-table-wrap">
          <h2>No settled bets in this range</h2>
          <p>Try widening the date range or clearing filters.</p>
        </div>`;
      return;
    }

    const body = rows
      .map(
        (b) => `
      <tr>
        <td class="mono">${escapeHtml(b.date_label || "—")}</td>
        <td>
          <div class="bets-fixture">
            <span class="bets-fixture__name">${escapeHtml(b.fixture || "—")}</span>
            <span class="bets-fixture__league">${escapeHtml(b.league || "")}</span>
          </div>
        </td>
        <td>${escapeHtml(b.strategy_short || "")}</td>
        <td>${escapeHtml(b.market || "—")}</td>
        <td class="mono">${fmtInr(b.stake_inr).replace("+", "")}</td>
        <td class="mono">${fmtOdds(b.odds)}</td>
        <td>${resultPill(b.result)}</td>
        <td>${pnlCell(b.pnl_inr)}</td>
      </tr>`
      )
      .join("");

    root.innerHTML = `
      <div class="bets-table-wrap">
        <table class="bets-table">
          <thead>
            <tr>
              <th scope="col" data-sort="time" tabindex="0" aria-sort="${sortKey === "time" ? (sortDir === "asc" ? "ascending" : "descending") : "none"}">Date</th>
              <th scope="col">Fixture</th>
              <th scope="col">Strategy</th>
              <th scope="col">Market</th>
              <th scope="col">Stake</th>
              <th scope="col">Odds</th>
              <th scope="col">Result</th>
              <th scope="col" data-sort="pnl_inr" tabindex="0" aria-sort="${sortKey === "pnl_inr" ? (sortDir === "asc" ? "ascending" : "descending") : "none"}">P&amp;L</th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>`;

    root.querySelectorAll("th[data-sort]").forEach((th) => {
      th.addEventListener("click", () => toggleSort(th.dataset.sort));
      th.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          toggleSort(th.dataset.sort);
        }
      });
    });
  }

  function toggleSort(key) {
    if (sortKey === key) sortDir = sortDir === "asc" ? "desc" : "asc";
    else {
      sortKey = key;
      sortDir = key === "time" ? "desc" : "desc";
    }
    render();
  }

  async function reload(page) {
    const params = new URLSearchParams();
    if (strategyFilter.value) params.set("strategy", strategyFilter.value);
    if (resultFilter.value) params.set("result", resultFilter.value);
    const days = Number(daysFilter.value);
    if (days > 0) params.set("days", String(days));
    else params.set("days", "0");
    params.set("page", String(page || 1));
    params.set("page_size", String(state.page_size || 50));
    const res = await fetch(`/api/bets/log?${params.toString()}`);
    state = await res.json();
    render();
  }

  fillStrategies();
  render();

  strategyFilter.addEventListener("change", () => reload(1));
  resultFilter.addEventListener("change", () => reload(1));
  daysFilter.addEventListener("change", () => reload(1));
  prevPage.addEventListener("click", () => reload(Math.max(1, (state.page || 1) - 1)));
  nextPage.addEventListener("click", () => reload((state.page || 1) + 1));
})();
