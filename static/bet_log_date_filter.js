/**
 * Shared date scope for strategy bet logs under Logs.
 * Default: today (IST). Modes: today | all | date (YYYY-MM-DD).
 */
(function (global) {
  "use strict";

  const IST = "Asia/Kolkata";

  function todayIstIso() {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: IST,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date());
    const y = parts.find((p) => p.type === "year")?.value;
    const m = parts.find((p) => p.type === "month")?.value;
    const d = parts.find((p) => p.type === "day")?.value;
    return `${y}-${m}-${d}`;
  }

  function entryDateIst(value) {
    if (!value) return "";
    const text = String(value).trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
    const d = new Date(text);
    if (Number.isNaN(d.getTime())) {
      const m = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/);
      if (m) {
        return `${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}`;
      }
      return "";
    }
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: IST,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(d);
    const y = parts.find((p) => p.type === "year")?.value;
    const m = parts.find((p) => p.type === "month")?.value;
    const day = parts.find((p) => p.type === "day")?.value;
    return `${y}-${m}-${day}`;
  }

  function filterEntries(entries, mode, dateIso, getDate) {
    const list = Array.isArray(entries) ? entries : [];
    if (mode === "all") return list.slice();
    const target = mode === "date" && dateIso ? dateIso : todayIstIso();
    const getter =
      getDate ||
      ((e) => e.fixture_date || e.created_at || e.kickoff || e.time || "");
    return list.filter((e) => entryDateIst(getter(e)) === target);
  }

  function avgOdds(entries) {
    const odds = entries
      .map((e) => Number(e.odds))
      .filter((o) => Number.isFinite(o) && o > 1);
    if (!odds.length) return null;
    return Math.round((odds.reduce((a, b) => a + b, 0) / odds.length) * 1000) / 1000;
  }

  function statusOf(e) {
    return String(e.status || e.result || "open").toLowerCase();
  }

  function computeDashboard(entries) {
    const list = Array.isArray(entries) ? entries : [];
    const placed = list.length;
    const won = list.filter((e) => statusOf(e) === "won").length;
    const lost = list.filter((e) => statusOf(e) === "lost").length;
    const push = list.filter((e) => statusOf(e) === "push").length;
    const open = list.filter((e) => statusOf(e) === "open").length;
    const decided = won + lost;
    const win_pct = decided ? Math.round((won / decided) * 1000) / 10 : 0;
    const unit_pnl =
      Math.round(
        list.reduce((s, e) => s + (Number(e.pnl_units) || 0), 0) * 1000
      ) / 1000;
    return {
      placed,
      won,
      lost,
      push,
      open,
      win_pct,
      avg_odds: avgOdds(list),
      unit_pnl,
    };
  }

  function readUrlState() {
    const params = new URLSearchParams(window.location.search);
    if (params.get("show") === "all") return { mode: "all", date: null };
    const date = params.get("date");
    if (date && /^\d{4}-\d{2}-\d{2}$/.test(date)) return { mode: "date", date };
    return { mode: "today", date: todayIstIso() };
  }

  function writeUrlState(mode, date) {
    const params = new URLSearchParams(window.location.search);
    params.delete("show");
    params.delete("date");
    if (mode === "all") params.set("show", "all");
    else if (mode === "date" && date) params.set("date", date);
    const qs = params.toString();
    const url = window.location.pathname + (qs ? `?${qs}` : "") + window.location.hash;
    window.history.replaceState({}, "", url);
  }

  /**
   * Wrap a page render(data) so it defaults to today and supports Show all / date.
   * options:
   *   getDate(entry) -> date source
   *   countKey: key for meta count (default "entries")
   *   transform(raw, mode, dateIso) -> payload passed to renderFn
   *   computeDashboard(entries) -> override dashboard builder
   */
  function attach(renderFn, options) {
    const opts = options || {};
    const getDate = opts.getDate;
    const metaEl = document.getElementById("betLogDateMeta");
    const dateInput = document.getElementById("betLogDateInput");
    const btnToday = document.getElementById("betLogDateToday");
    const btnAll = document.getElementById("betLogDateAll");
    const btnApply = document.getElementById("betLogDateApply");

    let raw = {};
    let state = readUrlState();

    function syncControls() {
      if (dateInput) {
        dateInput.value =
          state.mode === "date" ? state.date || todayIstIso() : todayIstIso();
      }
      if (btnToday) btnToday.classList.toggle("is-active", state.mode === "today");
      if (btnAll) btnAll.classList.toggle("is-active", state.mode === "all");
    }

    function updateMeta(shown, total) {
      if (!metaEl) return;
      if (state.mode === "all") {
        metaEl.textContent = `Showing all ${total} bets`;
      } else if (state.mode === "date") {
        metaEl.textContent = `Showing ${shown} of ${total} on ${state.date}`;
      } else {
        metaEl.textContent = `Showing today (${todayIstIso()}): ${shown} of ${total}`;
      }
    }

    function apply() {
      syncControls();
      writeUrlState(state.mode, state.date);
      const dateIso = state.date || todayIstIso();
      let payload;
      if (typeof opts.transform === "function") {
        payload = opts.transform(raw, state.mode, dateIso);
      } else {
        const allEntries = Array.isArray(raw.entries) ? raw.entries : [];
        const filtered = filterEntries(allEntries, state.mode, dateIso, getDate);
        const dashFn = opts.computeDashboard || computeDashboard;
        if (state.mode === "all") {
          payload = { ...raw, entries: allEntries };
        } else {
          payload = {
            ...raw,
            entries: filtered,
            dashboard: {
              ...(raw.dashboard || {}),
              ...dashFn(filtered),
            },
          };
        }
      }
      const countKey = opts.countKey || "entries";
      const shown = Array.isArray(payload[countKey]) ? payload[countKey].length : 0;
      const total = Array.isArray(raw[countKey])
        ? raw[countKey].length
        : Array.isArray(raw.entries)
          ? raw.entries.length
          : 0;
      updateMeta(shown, total);
      renderFn(payload);
    }

    function wrappedRender(data) {
      if (data && typeof data === "object") {
        raw = { ...data };
        if (Array.isArray(data.entries)) raw.entries = data.entries;
        if (Array.isArray(data.baskets)) raw.baskets = data.baskets;
      }
      apply();
    }

    if (btnToday) {
      btnToday.addEventListener("click", () => {
        state = { mode: "today", date: todayIstIso() };
        apply();
      });
    }
    if (btnAll) {
      btnAll.addEventListener("click", () => {
        state = { mode: "all", date: null };
        apply();
      });
    }
    if (btnApply && dateInput) {
      btnApply.addEventListener("click", () => {
        const v = dateInput.value;
        if (!v) return;
        state = { mode: "date", date: v };
        apply();
      });
      dateInput.addEventListener("change", () => {
        if (!dateInput.value) return;
        state = { mode: "date", date: dateInput.value };
        apply();
      });
    }

    syncControls();
    return wrappedRender;
  }

  global.BetLogDateFilter = {
    todayIstIso,
    entryDateIst,
    filterEntries,
    computeDashboard,
    attach,
  };
})(window);
