(function () {
  "use strict";

  const root = document.getElementById("betsRoot");
  const rangePill = document.getElementById("rangePill");
  const strategyFilter = document.getElementById("strategyFilter");
  const resultFilter = document.getElementById("resultFilter");
  const pager = document.getElementById("pager");
  const pagerMeta = document.getElementById("pagerMeta");
  const prevPage = document.getElementById("prevPage");
  const nextPage = document.getElementById("nextPage");

  const rangeTrigger = document.getElementById("rangeTrigger");
  const rangeTriggerText = document.getElementById("rangeTriggerText");
  const rangePopover = document.getElementById("rangePopover");
  const calGrid = document.getElementById("calGrid");
  const calMonthLabel = document.getElementById("calMonthLabel");
  const calHint = document.getElementById("calHint");
  const calPrev = document.getElementById("calPrev");
  const calNext = document.getElementById("calNext");
  const calApply = document.getElementById("calApply");
  const calClear = document.getElementById("calClear");
  const presetBtns = Array.from(document.querySelectorAll("[data-preset]"));

  let state = window.INITIAL_BET_LOG || { entries: [], strategies: [], page: 1, pages: 1 };
  let sortKey = "time";
  let sortDir = "asc";

  /** @type {{ mode: "days"|"range"|"all", days: number|null, from: string|null, to: string|null }} */
  let filter = {
    mode: "days",
    days: 30,
    from: state.date_from || null,
    to: state.date_to || null,
  };

  if (state.date_from && state.date_to && state.range_days == null) {
    filter.mode = "range";
    filter.days = null;
  } else if (state.range_days === 0 || (state.date_from == null && state.range_days == null)) {
    // Initial payload with days=30 always sets date_from/to; keep days mode.
    filter.mode = "days";
    filter.days = state.range_days != null ? state.range_days : 30;
  }

  let draftFrom = filter.from;
  let draftTo = filter.to;
  let pickingEnd = false;
  let viewYear;
  let viewMonth; // 0-indexed

  function todayIso() {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Kolkata",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date());
  }

  function addDaysIso(iso, delta) {
    const [y, m, d] = iso.split("-").map(Number);
    const dt = new Date(Date.UTC(y, m - 1, d));
    dt.setUTCDate(dt.getUTCDate() + delta);
    return dt.toISOString().slice(0, 10);
  }

  function initViewMonth() {
    const anchor = draftTo || draftFrom || todayIso();
    const [y, m] = anchor.split("-").map(Number);
    viewYear = y;
    viewMonth = m - 1;
  }

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

  function triggerLabel() {
    if (filter.mode === "all") return "All time";
    if (filter.mode === "days" && filter.days) return `Last ${filter.days} days`;
    if (filter.from && filter.to && filter.from === filter.to) return filter.from;
    if (filter.from && filter.to) return `${filter.from} → ${filter.to}`;
    if (filter.from) return filter.from;
    return "Pick dates";
  }

  function syncTrigger() {
    rangeTriggerText.textContent = triggerLabel();
    presetBtns.forEach((btn) => {
      const p = btn.getAttribute("data-preset");
      let active = false;
      if (p === "all") active = filter.mode === "all";
      else if (filter.mode === "days") active = String(filter.days) === p;
      btn.classList.toggle("is-active", active);
    });
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
    syncTrigger();
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
        <table class="bets-table" data-column-filters="1">
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Fixture</th>
              <th scope="col">Strategy</th>
              <th scope="col">Market</th>
              <th scope="col">Stake</th>
              <th scope="col">Odds</th>
              <th scope="col">Result</th>
              <th scope="col">P&amp;L</th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>`;

    if (window.TableTools) {
      window.TableTools.enhanceTable(root.querySelector("table"));
    }
  }

  function orderedDraft() {
    if (!draftFrom) return { from: null, to: null };
    if (!draftTo) return { from: draftFrom, to: draftFrom };
    return draftFrom <= draftTo
      ? { from: draftFrom, to: draftTo }
      : { from: draftTo, to: draftFrom };
  }

  function updateHint() {
    const { from, to } = orderedDraft();
    if (!from) {
      calHint.textContent = "Click a day, or click two days for a range.";
    } else if (pickingEnd && from === to) {
      calHint.textContent = `Selected ${from}. Click another day to extend the range, or Apply.`;
    } else if (from === to) {
      calHint.textContent = `Single day: ${from}`;
    } else {
      calHint.textContent = `Range: ${from} → ${to}`;
    }
  }

  function renderCalendar() {
    const monthNames = [
      "January", "February", "March", "April", "May", "June",
      "July", "August", "September", "October", "November", "December",
    ];
    calMonthLabel.textContent = `${monthNames[viewMonth]} ${viewYear}`;

    const first = new Date(viewYear, viewMonth, 1);
    // Monday-first: JS getDay() Sun=0 → shift
    let startPad = (first.getDay() + 6) % 7;
    const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
    const prevDays = new Date(viewYear, viewMonth, 0).getDate();

    const { from, to } = orderedDraft();
    const today = todayIso();
    const cells = [];

    for (let i = 0; i < 42; i++) {
      let y = viewYear;
      let m = viewMonth;
      let day;
      let outside = false;
      if (i < startPad) {
        day = prevDays - startPad + i + 1;
        m -= 1;
        if (m < 0) {
          m = 11;
          y -= 1;
        }
        outside = true;
      } else if (i >= startPad + daysInMonth) {
        day = i - startPad - daysInMonth + 1;
        m += 1;
        if (m > 11) {
          m = 0;
          y += 1;
        }
        outside = true;
      } else {
        day = i - startPad + 1;
      }
      const iso = `${y}-${String(m + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
      const classes = ["bets-cal__day"];
      if (outside) classes.push("is-outside");
      if (iso === today) classes.push("is-today");
      if (from && to && iso >= from && iso <= to) classes.push("is-in-range");
      if (from && iso === from) classes.push("is-range-start", "is-selected");
      if (to && iso === to) classes.push("is-range-end", "is-selected");
      cells.push(
        `<button type="button" class="${classes.join(" ")}" data-date="${iso}" ${
          outside ? "tabindex='-1'" : ""
        }>${day}</button>`
      );
    }
    calGrid.innerHTML = cells.join("");
    updateHint();
  }

  function openPopover() {
    draftFrom = filter.from;
    draftTo = filter.to;
    pickingEnd = false;
    if (filter.mode === "days" && filter.days) {
      const end = todayIso();
      draftTo = end;
      draftFrom = addDaysIso(end, -(filter.days - 1));
    } else if (filter.mode === "all") {
      draftFrom = null;
      draftTo = null;
    }
    initViewMonth();
    rangePopover.hidden = false;
    rangeTrigger.setAttribute("aria-expanded", "true");
    renderCalendar();
  }

  function closePopover() {
    rangePopover.hidden = true;
    rangeTrigger.setAttribute("aria-expanded", "false");
  }

  function togglePopover() {
    if (rangePopover.hidden) openPopover();
    else closePopover();
  }

  async function reload(page) {
    const params = new URLSearchParams();
    if (strategyFilter.value) params.set("strategy", strategyFilter.value);
    if (resultFilter.value) params.set("result", resultFilter.value);
    if (filter.mode === "all") {
      params.set("days", "0");
    } else if (filter.mode === "days" && filter.days) {
      params.set("days", String(filter.days));
    } else if (filter.from) {
      params.set("date_from", filter.from);
      params.set("date_to", filter.to || filter.from);
    } else {
      params.set("days", "30");
    }
    params.set("page", String(page || 1));
    params.set("page_size", String(state.page_size || 50));
    const res = await fetch(`/api/bets/log?${params.toString()}`);
    state = await res.json();
    if (state.date_from) filter.from = state.date_from;
    if (state.date_to) filter.to = state.date_to;
    render();
  }

  function applyDraft() {
    const { from, to } = orderedDraft();
    if (!from) {
      filter = { mode: "all", days: null, from: null, to: null };
    } else {
      filter = { mode: "range", days: null, from, to };
    }
    closePopover();
    reload(1);
  }

  function applyPreset(preset) {
    if (preset === "all") {
      filter = { mode: "all", days: null, from: null, to: null };
      draftFrom = null;
      draftTo = null;
    } else {
      const days = Number(preset);
      const end = todayIso();
      const start = addDaysIso(end, -(days - 1));
      filter = { mode: "days", days, from: start, to: end };
      draftFrom = start;
      draftTo = end;
    }
    pickingEnd = false;
    initViewMonth();
    renderCalendar();
    closePopover();
    reload(1);
  }

  calGrid.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-date]");
    if (!btn) return;
    const iso = btn.getAttribute("data-date");
    if (!iso) return;

    if (!draftFrom || (draftFrom && draftTo && !pickingEnd)) {
      draftFrom = iso;
      draftTo = iso;
      pickingEnd = true;
    } else {
      draftTo = iso;
      pickingEnd = false;
    }
    renderCalendar();
  });

  rangeTrigger.addEventListener("click", (e) => {
    e.stopPropagation();
    togglePopover();
  });
  rangePopover.addEventListener("click", (e) => e.stopPropagation());
  document.addEventListener("click", () => {
    if (!rangePopover.hidden) closePopover();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !rangePopover.hidden) closePopover();
  });

  calPrev.addEventListener("click", () => {
    viewMonth -= 1;
    if (viewMonth < 0) {
      viewMonth = 11;
      viewYear -= 1;
    }
    renderCalendar();
  });
  calNext.addEventListener("click", () => {
    viewMonth += 1;
    if (viewMonth > 11) {
      viewMonth = 0;
      viewYear += 1;
    }
    renderCalendar();
  });
  calApply.addEventListener("click", applyDraft);
  calClear.addEventListener("click", () => {
    draftFrom = null;
    draftTo = null;
    pickingEnd = false;
    renderCalendar();
  });
  presetBtns.forEach((btn) => {
    btn.addEventListener("click", () => applyPreset(btn.getAttribute("data-preset")));
  });

  fillStrategies();
  // Seed filter bounds from initial payload (last-30 default).
  if (state.date_from && state.date_to) {
    filter.from = state.date_from;
    filter.to = state.date_to;
    if (state.range_days) {
      filter.mode = "days";
      filter.days = state.range_days;
    } else {
      filter.mode = "range";
      filter.days = null;
    }
  }
  render();

  strategyFilter.addEventListener("change", () => reload(1));
  resultFilter.addEventListener("change", () => reload(1));
  prevPage.addEventListener("click", () => reload(Math.max(1, (state.page || 1) - 1)));
  nextPage.addEventListener("click", () => reload((state.page || 1) + 1));
})();
