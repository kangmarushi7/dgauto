(function () {
  "use strict";

  const STATUS_ORDER = ["open", "won", "lost", "push"];

  function inferType(raw) {
    const value = (raw || "").trim();
    if (!value) return { type: "text", value: "" };

    const pct = value.endsWith("%") ? value.slice(0, -1) : value;
    const num = Number(pct);
    if (!Number.isNaN(num)) return { type: "number", value: num };

    const ts = Date.parse(value);
    if (!Number.isNaN(ts) && value.includes("-")) return { type: "date", value: ts };

    return { type: "text", value: value.toLowerCase() };
  }

  function compareCells(a, b, direction) {
    if (a.type === b.type) {
      if (a.value < b.value) return direction === "asc" ? -1 : 1;
      if (a.value > b.value) return direction === "asc" ? 1 : -1;
      return 0;
    }
    const av = String(a.value);
    const bv = String(b.value);
    if (av < bv) return direction === "asc" ? -1 : 1;
    if (av > bv) return direction === "asc" ? 1 : -1;
    return 0;
  }

  function usesColumnFilters(table) {
    return table && table.dataset.columnFilters === "1";
  }

  function dataRows(table) {
    return Array.from(table.tBodies[0]?.rows || []).filter(
      (row) => !row.querySelector(".stats-empty"),
    );
  }

  function filterSourceCol(table, colIndex) {
    const th = table.tHead?.rows?.[0]?.cells?.[colIndex];
    if (th?.dataset.filterSourceCol != null) {
      const n = parseInt(th.dataset.filterSourceCol, 10);
      if (!Number.isNaN(n)) return n;
    }
    return colIndex;
  }

  function getFilterValue(row, colIndex, table) {
    const src = filterSourceCol(table, colIndex);
    const cell = row.cells[src];
    if (!cell) return "";
    return (cell.textContent || "").trim();
  }

  function formatFilterLabel(value) {
    if (!value) return "(empty)";
    const lower = value.toLowerCase();
    if (STATUS_ORDER.includes(lower)) {
      return lower.charAt(0).toUpperCase() + lower.slice(1);
    }
    return value;
  }

  function sortFilterValues(values, colIndex, table) {
    const statusLike = values.every((v) => {
      const k = v.toLowerCase();
      return !k || STATUS_ORDER.includes(k);
    });
    if (statusLike) {
      return values.sort((a, b) => {
        const ai = STATUS_ORDER.indexOf(a.toLowerCase());
        const bi = STATUS_ORDER.indexOf(b.toLowerCase());
        if (ai === -1 && bi === -1) return a.localeCompare(b);
        if (ai === -1) return 1;
        if (bi === -1) return -1;
        return ai - bi;
      });
    }
    return values.sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
  }

  function collectColumnValues(table, colIndex) {
    const seen = new Map();
    for (const row of dataRows(table)) {
      const raw = getFilterValue(row, colIndex, table);
      const key = raw.toLowerCase();
      if (!seen.has(key)) seen.set(key, raw);
    }
    return sortFilterValues(Array.from(seen.values()), colIndex, table);
  }

  function closeFilterMenu(table) {
    const state = table._tableTools;
    if (!state?.openMenu) return;
    state.openMenu.remove();
    state.openMenu = null;
    document.removeEventListener("click", state.menuOutsideHandler);
    state.menuOutsideHandler = null;
  }

  function applyColumnFilters(table) {
    const state = table._tableTools;
    if (!state?.columnFilters) return;
    const filters = state.columnFilters;
    for (const row of dataRows(table)) {
      let show = true;
      for (const [colKey, selected] of Object.entries(filters)) {
        if (!selected) continue;
        const colIndex = parseInt(colKey, 10);
        const cellVal = getFilterValue(row, colIndex, table);
        if (cellVal.toLowerCase() !== selected.toLowerCase()) {
          show = false;
          break;
        }
      }
      row.style.display = show ? "" : "none";
    }
  }

  function applySearchFilter(table) {
    const state = table._tableTools;
    if (!state?.input) return;
    const needle = (state.input.value || "").trim().toLowerCase();
    const rows = Array.from(table.tBodies[0]?.rows || []);
    for (const row of rows) {
      if (!needle) {
        row.style.display = "";
        continue;
      }
      const text = (row.textContent || "").toLowerCase();
      row.style.display = text.includes(needle) ? "" : "none";
    }
  }

  function applyFilter(table) {
    if (usesColumnFilters(table)) applyColumnFilters(table);
    else applySearchFilter(table);
  }

  function applySort(table) {
    const state = table._tableTools;
    if (!state || state.sortIndex < 0) return;
    const tbody = table.tBodies[0];
    if (!tbody) return;
    const rows = Array.from(tbody.rows);
    rows.sort((ra, rb) => {
      const ac = inferType(ra.cells[state.sortIndex]?.textContent || "");
      const bc = inferType(rb.cells[state.sortIndex]?.textContent || "");
      return compareCells(ac, bc, state.direction);
    });
    for (const row of rows) tbody.appendChild(row);
  }

  function markHeaderSort(table) {
    const state = table._tableTools;
    if (!state) return;
    const headers = Array.from(table.tHead?.rows?.[0]?.cells || []);
    headers.forEach((h, idx) => {
      const label = h.querySelector(".th-label") || h;
      label.classList.remove("sort-asc", "sort-desc");
      if (idx === state.sortIndex) {
        label.classList.add(state.direction === "asc" ? "sort-asc" : "sort-desc");
      }
    });
  }

  function updateFilterButtonState(table, colIndex) {
    const th = table.tHead?.rows?.[0]?.cells?.[colIndex];
    const btn = th?.querySelector(".col-filter-btn");
    if (!btn) return;
    const active = table._tableTools?.columnFilters?.[colIndex];
    btn.classList.toggle("col-filter-btn--active", Boolean(active));
  }

  function openFilterMenu(table, colIndex, btn) {
    closeFilterMenu(table);
    const state = table._tableTools;
    const values = collectColumnValues(table, colIndex);
    const current = state.columnFilters[colIndex] || null;

    const menu = document.createElement("div");
    menu.className = "col-filter-menu";
    menu.setAttribute("role", "listbox");

    function addOption(label, value) {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "col-filter-option";
      item.setAttribute("role", "option");
      item.textContent = label;
      if ((value == null && !current) || (value && current && value.toLowerCase() === current.toLowerCase())) {
        item.classList.add("is-selected");
        item.setAttribute("aria-selected", "true");
      }
      item.addEventListener("click", (e) => {
        e.stopPropagation();
        if (value == null) delete state.columnFilters[colIndex];
        else state.columnFilters[colIndex] = value;
        applyFilter(table);
        updateFilterButtonState(table, colIndex);
        closeFilterMenu(table);
      });
      menu.appendChild(item);
    }

    addOption("All", null);
    for (const v of values) addOption(formatFilterLabel(v), v);

    document.body.appendChild(menu);
    const rect = btn.getBoundingClientRect();
    menu.style.position = "fixed";
    menu.style.left = `${Math.max(8, rect.left)}px`;
    menu.style.top = `${rect.bottom + 4}px`;
    menu.style.minWidth = `${Math.max(120, rect.width + 40)}px`;
    menu.style.zIndex = "10000";

    state.openMenu = menu;

    state.menuOutsideHandler = (e) => {
      if (menu.contains(e.target) || btn.contains(e.target)) return;
      closeFilterMenu(table);
    };
    setTimeout(() => document.addEventListener("click", state.menuOutsideHandler), 0);
  }

  function wireSort(table, labelEl, colIndex) {
    labelEl.classList.add("sortable-header");
    labelEl.addEventListener("click", function () {
      const state = table._tableTools;
      if (state.sortIndex === colIndex) {
        state.direction = state.direction === "asc" ? "desc" : "asc";
      } else {
        state.sortIndex = colIndex;
        state.direction = "asc";
      }
      applySort(table);
      applyFilter(table);
      markHeaderSort(table);
    });
  }

  function buildColumnHeaders(table) {
    const headers = Array.from(table.tHead.rows[0].cells);
    headers.forEach((th, idx) => {
      if (th.querySelector(".th-inner")) return;
      const label = (th.dataset.filterLabel || th.textContent || "").trim();
      th.textContent = "";
      th.classList.add("th-filterable");

      const inner = document.createElement("div");
      inner.className = "th-inner";

      const labelSpan = document.createElement("span");
      labelSpan.className = "th-label";
      labelSpan.textContent = label;

      const filterBtn = document.createElement("button");
      filterBtn.type = "button";
      filterBtn.className = "col-filter-btn";
      filterBtn.setAttribute("aria-label", `Filter by ${label}`);
      filterBtn.setAttribute("aria-haspopup", "listbox");
      filterBtn.innerHTML = "&#9662;";

      filterBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (table._tableTools.openMenu && table._tableTools.openCol === idx) {
          closeFilterMenu(table);
          return;
        }
        table._tableTools.openCol = idx;
        openFilterMenu(table, idx, filterBtn);
      });

      inner.appendChild(labelSpan);
      inner.appendChild(filterBtn);
      th.appendChild(inner);
      wireSort(table, labelSpan, idx);
    });
  }

  function enhanceWithColumnFilters(table) {
    table.classList.add("sortable-filterable", "column-filterable");
    table._tableTools = {
      sortIndex: -1,
      direction: "asc",
      columnFilters: {},
      openMenu: null,
      openCol: -1,
      menuOutsideHandler: null,
    };
    buildColumnHeaders(table);
  }

  function enhanceWithSearchFilter(table) {
    table.classList.add("sortable-filterable");

    const controls = document.createElement("div");
    controls.className = "table-tools";
    const input = document.createElement("input");
    input.type = "search";
    input.placeholder = "Filter table...";
    input.className = "table-filter-input";
    controls.appendChild(input);
    table.parentNode.insertBefore(controls, table);

    table._tableTools = { input, sortIndex: -1, direction: "asc" };

    const headers = Array.from(table.tHead.rows[0].cells);
    headers.forEach((h, idx) => {
      h.classList.add("sortable-header");
      h.addEventListener("click", function () {
        const state = table._tableTools;
        if (state.sortIndex === idx) {
          state.direction = state.direction === "asc" ? "desc" : "asc";
        } else {
          state.sortIndex = idx;
          state.direction = "asc";
        }
        applySort(table);
        applyFilter(table);
        markHeaderSort(table);
      });
    });

    input.addEventListener("input", function () {
      applyFilter(table);
    });
  }

  function enhanceTable(table) {
    if (!table || table.dataset.tableEnhanced === "1") return;
    if (!table.tHead || !table.tBodies.length) return;

    table.dataset.tableEnhanced = "1";

    if (usesColumnFilters(table)) enhanceWithColumnFilters(table);
    else enhanceWithSearchFilter(table);
  }

  function enhanceAll() {
    document.querySelectorAll("table").forEach(enhanceTable);
  }

  function reapply(table) {
    if (!table || !table._tableTools) return;
    applySort(table);
    applyFilter(table);
    markHeaderSort(table);
    if (usesColumnFilters(table)) {
      Array.from(table.tHead?.rows?.[0]?.cells || []).forEach((_, idx) =>
        updateFilterButtonState(table, idx),
      );
    }
  }

  function boot() {
    enhanceAll();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  window.TableTools = { enhanceTable, enhanceAll, reapply, closeFilterMenu };
})();
