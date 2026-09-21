(function () {
  "use strict";

  const state = window.TRADE_PICKS_STATE || { pick_date: null, include_settled: false };
  const categoryFilter = document.getElementById("categoryFilter");
  const strategyFilter = document.getElementById("strategyFilter");
  const includeSettled = document.getElementById("includeSettled");
  const exportCsv = document.getElementById("exportCsv");
  const table = document.getElementById("tradePicksTable");
  const kpiShown = document.getElementById("kpiShown");
  const kpiOpen = document.getElementById("kpiOpen");
  const kpiSettled = document.getElementById("kpiSettled");
  const kpiPnl = document.getElementById("kpiPnl");
  const kpiRoi = document.getElementById("kpiRoi");

  const dateTrigger = document.getElementById("dateTrigger");
  const dateTriggerText = document.getElementById("dateTriggerText");
  const datePopover = document.getElementById("datePopover");
  const calPrev = document.getElementById("calPrev");
  const calNext = document.getElementById("calNext");
  const calMonthLabel = document.getElementById("calMonthLabel");
  const calGrid = document.getElementById("calGrid");
  const calClear = document.getElementById("calClear");
  const calApply = document.getElementById("calApply");

  let draftDate = state.pick_date || null;
  let viewYear;
  let viewMonth;

  function todayIso() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function initViewMonth() {
    const base = draftDate || state.pick_date || todayIso();
    const [y, m] = base.split("-").map(Number);
    viewYear = y;
    viewMonth = m - 1;
  }

  function monthLabel(y, m) {
    return new Date(y, m, 1).toLocaleString(undefined, { month: "long", year: "numeric" });
  }

  function renderCalendar() {
    if (!calGrid || !calMonthLabel) return;
    calMonthLabel.textContent = monthLabel(viewYear, viewMonth);
    const first = new Date(viewYear, viewMonth, 1);
    // Monday-first pad
    let startPad = (first.getDay() + 6) % 7;
    const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
    const prevDays = new Date(viewYear, viewMonth, 0).getDate();
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
      if (draftDate && iso === draftDate) classes.push("is-selected");
      cells.push(
        `<button type="button" class="${classes.join(" ")}" data-date="${iso}">${day}</button>`
      );
    }
    calGrid.innerHTML = cells.join("");
  }

  function openPopover() {
    draftDate = state.pick_date || null;
    initViewMonth();
    datePopover.hidden = false;
    dateTrigger.setAttribute("aria-expanded", "true");
    renderCalendar();
  }

  function closePopover() {
    datePopover.hidden = true;
    dateTrigger.setAttribute("aria-expanded", "false");
  }

  function navigateTo(pickDate, settled) {
    const params = new URLSearchParams();
    if (pickDate) params.set("date", pickDate);
    else if (settled) params.set("include_settled", "1");
    const q = params.toString();
    window.location.search = q ? "?" + q : "";
  }

  function queryParams() {
    const params = new URLSearchParams();
    if (state.pick_date) params.set("date", state.pick_date);
    else if (includeSettled && includeSettled.checked) params.set("include_settled", "1");
    if (categoryFilter && categoryFilter.value) params.set("category", categoryFilter.value);
    if (strategyFilter && strategyFilter.value) params.set("strategy", strategyFilter.value);
    return params;
  }

  function syncExportHref() {
    if (!exportCsv) return;
    const q = queryParams().toString();
    exportCsv.href = "/api/trade-picks/export" + (q ? "?" + q : "");
  }

  function setTone(el, value) {
    if (!el) return;
    el.classList.remove("bets-pos", "bets-neg");
    if (value > 0) el.classList.add("bets-pos");
    else if (value < 0) el.classList.add("bets-neg");
  }

  function applyClientFilters() {
    if (!table) {
      syncExportHref();
      return;
    }
    const cat = (categoryFilter && categoryFilter.value) || "";
    const strat = (strategyFilter && strategyFilter.value) || "";
    let shown = 0;
    let open = 0;
    let settled = 0;
    let pnl = 0;
    for (const row of table.tBodies[0]?.rows || []) {
      const matchCat = !cat || row.dataset.category === cat;
      const matchStrat =
        !strat ||
        row.dataset.strategy === strat ||
        (strat === "arahus" && String(row.dataset.strategy || "").startsWith("arahus"));
      const visible = matchCat && matchStrat;
      row.hidden = !visible;
      if (!visible) continue;
      shown += 1;
      if (row.dataset.status === "open") open += 1;
      const result = String(row.dataset.result || "").toLowerCase();
      if (["won", "lost", "push"].includes(result)) {
        settled += 1;
        const p = Number(row.dataset.pnl);
        if (!Number.isNaN(p)) pnl += p;
      }
    }
    if (kpiShown) kpiShown.textContent = String(shown);
    if (kpiOpen) kpiOpen.textContent = String(open);
    if (kpiSettled) kpiSettled.textContent = String(settled);
    if (kpiPnl) {
      if (settled) {
        kpiPnl.textContent = `${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}`;
        setTone(kpiPnl, pnl);
      } else {
        kpiPnl.textContent = "—";
        setTone(kpiPnl, 0);
      }
    }
    if (kpiRoi) {
      if (settled) {
        const roiPct = (pnl / settled) * 100;
        kpiRoi.textContent = `${roiPct >= 0 ? "+" : ""}${roiPct.toFixed(1)}%`;
        setTone(kpiRoi, roiPct);
      } else {
        kpiRoi.textContent = "—";
        setTone(kpiRoi, 0);
      }
    }
    syncExportHref();
  }

  if (dateTrigger) {
    dateTrigger.addEventListener("click", (e) => {
      e.stopPropagation();
      if (datePopover.hidden) openPopover();
      else closePopover();
    });
  }
  if (calPrev) {
    calPrev.addEventListener("click", (e) => {
      e.stopPropagation();
      viewMonth -= 1;
      if (viewMonth < 0) {
        viewMonth = 11;
        viewYear -= 1;
      }
      renderCalendar();
    });
  }
  if (calNext) {
    calNext.addEventListener("click", (e) => {
      e.stopPropagation();
      viewMonth += 1;
      if (viewMonth > 11) {
        viewMonth = 0;
        viewYear += 1;
      }
      renderCalendar();
    });
  }
  if (calGrid) {
    calGrid.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-date]");
      if (!btn) return;
      e.stopPropagation();
      draftDate = btn.getAttribute("data-date");
      renderCalendar();
    });
  }
  if (calApply) {
    calApply.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      navigateTo(draftDate, includeSettled && includeSettled.checked);
    });
  }
  if (calClear) {
    calClear.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      draftDate = null;
      navigateTo(null, false);
    });
  }
  document.querySelectorAll("[data-preset]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const preset = btn.getAttribute("data-preset");
      if (preset === "today") {
        draftDate = todayIso();
        renderCalendar();
      } else if (preset === "clear") {
        draftDate = null;
        navigateTo(null, false);
      }
    });
  });
  document.addEventListener("click", (e) => {
    if (!datePopover || datePopover.hidden) return;
    if (e.target.closest("#datePicker")) return;
    closePopover();
  });

  if (categoryFilter) categoryFilter.addEventListener("change", applyClientFilters);
  if (strategyFilter) strategyFilter.addEventListener("change", applyClientFilters);

  if (includeSettled && !includeSettled.disabled) {
    includeSettled.addEventListener("change", () => {
      navigateTo(state.pick_date, includeSettled.checked);
    });
  }

  if (dateTriggerText) {
    dateTriggerText.textContent = state.pick_date || "All open";
  }

  syncExportHref();
  applyClientFilters();
})();
