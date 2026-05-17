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

  function normalizeFilterSet(selected, allValues) {
    if (!selected || selected.size === 0) return null;
    if (selected.size >= allValues.length) return null;
    return selected;
  }

  function applyColumnFilters(table) {
    const state = table._tableTools;
    if (!state?.columnFilters) return;
    const filters = state.columnFilters;
    for (const row of dataRows(table)) {
      let show = true;
      for (const [colKey, selectedSet] of Object.entries(filters)) {
        if (!selectedSet || selectedSet.size === 0) continue;
        const colIndex = parseInt(colKey, 10);
        const allValues = collectColumnValues(table, colIndex);
        if (selectedSet.size >= allValues.length) continue;
        const cellVal = getFilterValue(row, colIndex, table).toLowerCase();
        if (!selectedSet.has(cellVal)) {
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

  function isColumnFilterActive(table, colIndex) {
    const set = table._tableTools?.columnFilters?.[colIndex];
    if (!set || set.size === 0) return false;
    const allValues = collectColumnValues(table, colIndex);
    return set.size < allValues.length;
  }

  function updateFilterButtonState(table, colIndex) {
    const th = table.tHead?.rows?.[0]?.cells?.[colIndex];
    const btn = th?.querySelector(".col-filter-btn");
    if (!btn) return;
    btn.classList.toggle("col-filter-btn--active", isColumnFilterActive(table, colIndex));
  }

  function commitColumnFilter(table, colIndex, selectedSet, allValues) {
    const state = table._tableTools;
    const normalized = normalizeFilterSet(selectedSet, allValues);
    if (normalized) state.columnFilters[colIndex] = normalized;
    else delete state.columnFilters[colIndex];
    applyFilter(table);
    updateFilterButtonState(table, colIndex);
  }

  function positionPopover(menu, anchorEl) {
    const rect = anchorEl.getBoundingClientRect();
    const gap = 4;
    const margin = 8;
    menu.style.position = "fixed";
    menu.style.zIndex = "10000";
    document.body.appendChild(menu);
    const menuRect = menu.getBoundingClientRect();
    let left = rect.left;
    let top = rect.bottom + gap;
    if (left + menuRect.width > window.innerWidth - margin) {
      left = window.innerWidth - menuRect.width - margin;
    }
    if (left < margin) left = margin;
    if (top + menuRect.height > window.innerHeight - margin) {
      top = rect.top - menuRect.height - gap;
    }
    if (top < margin) top = margin;
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
  }

  function openFilterMenu(table, colIndex, btn) {
    closeFilterMenu(table);
    const state = table._tableTools;
    const th = table.tHead?.rows?.[0]?.cells?.[colIndex];
    const colLabel =
      th?.dataset.filterLabel || th?.querySelector(".th-label")?.textContent || "Column";
    const allValues = collectColumnValues(table, colIndex);
    const existing = state.columnFilters[colIndex];
    const selected = existing
      ? new Set(existing)
      : new Set(allValues.map((v) => v.toLowerCase()));

    const popover = document.createElement("div");
    popover.className = "excel-filter-popover";
    popover.setAttribute("role", "dialog");
    popover.style.background = "#1e2732";
    popover.style.border = "1px solid rgba(255,255,255,0.14)";
    popover.style.borderRadius = "8px";
    popover.style.boxShadow = "0 12px 40px rgba(0,0,0,0.65)";
    popover.addEventListener("click", (e) => e.stopPropagation());

    const title = document.createElement("div");
    title.className = "excel-filter-title";
    title.textContent = `Filter: ${colLabel}`;
    popover.appendChild(title);

    const sortRow = document.createElement("div");
    sortRow.className = "excel-filter-sort";
    const sortAsc = document.createElement("button");
    sortAsc.type = "button";
    sortAsc.className = "excel-filter-link";
    sortAsc.textContent = "Sort A → Z";
    const sortDesc = document.createElement("button");
    sortDesc.type = "button";
    sortDesc.className = "excel-filter-link";
    sortDesc.textContent = "Sort Z → A";
    sortAsc.addEventListener("click", () => {
      state.sortIndex = colIndex;
      state.direction = "asc";
      applySort(table);
      applyFilter(table);
      markHeaderSort(table);
    });
    sortDesc.addEventListener("click", () => {
      state.sortIndex = colIndex;
      state.direction = "desc";
      applySort(table);
      applyFilter(table);
      markHeaderSort(table);
    });
    sortRow.appendChild(sortAsc);
    sortRow.appendChild(sortDesc);
    popover.appendChild(sortRow);

    const searchWrap = document.createElement("div");
    searchWrap.className = "excel-filter-search-wrap";
    const search = document.createElement("input");
    search.type = "search";
    search.className = "excel-filter-search";
    search.placeholder = "Search…";
    searchWrap.appendChild(search);
    popover.appendChild(searchWrap);

    const list = document.createElement("div");
    list.className = "excel-filter-list";
    list.style.display = "flex";
    list.style.flexDirection = "column";
    list.style.alignItems = "stretch";
    list.style.maxHeight = "220px";
    list.style.overflowY = "auto";
    list.style.overflowX = "hidden";
    list.style.background = "#1e2732";

    const selectAllLabel = document.createElement("label");
    selectAllLabel.className = "excel-filter-row excel-filter-row--select-all";
    selectAllLabel.style.display = "flex";
    selectAllLabel.style.width = "100%";
    selectAllLabel.style.boxSizing = "border-box";
    const selectAllCb = document.createElement("input");
    selectAllCb.type = "checkbox";
    selectAllCb.checked = selected.size === allValues.length;
    const selectAllText = document.createElement("span");
    selectAllText.textContent = "(Select all)";
    selectAllLabel.appendChild(selectAllCb);
    selectAllLabel.appendChild(selectAllText);
    list.appendChild(selectAllLabel);

    const rowRefs = [];

    function syncSelectAll() {
      const visible = rowRefs.filter((r) => r.label.style.display !== "none");
      const checkedCount = visible.filter((r) => r.cb.checked).length;
      selectAllCb.indeterminate = checkedCount > 0 && checkedCount < visible.length;
      selectAllCb.checked = visible.length > 0 && checkedCount === visible.length;
    }

    function applyFromCheckboxes() {
      const next = new Set();
      for (const { value, cb } of rowRefs) {
        if (cb.checked) next.add(value.toLowerCase());
      }
      commitColumnFilter(table, colIndex, next, allValues);
    }

    for (const value of allValues) {
      const label = document.createElement("label");
      label.className = "excel-filter-row";
      label.style.display = "flex";
      label.style.width = "100%";
      label.style.boxSizing = "border-box";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = selected.has(value.toLowerCase());
      const text = document.createElement("span");
      text.textContent = formatFilterLabel(value);
      label.appendChild(cb);
      label.appendChild(text);
      list.appendChild(label);
      rowRefs.push({ value, cb, label });

      cb.addEventListener("change", () => {
        syncSelectAll();
        applyFromCheckboxes();
      });
    }

    selectAllCb.addEventListener("change", () => {
      const on = selectAllCb.checked;
      for (const { cb, label } of rowRefs) {
        if (label.style.display === "none") continue;
        cb.checked = on;
      }
      syncSelectAll();
      applyFromCheckboxes();
    });

    search.addEventListener("input", () => {
      const needle = search.value.trim().toLowerCase();
      for (const { label, value } of rowRefs) {
        const text = formatFilterLabel(value).toLowerCase();
        label.style.display = !needle || text.includes(needle) ? "" : "none";
      }
      syncSelectAll();
    });

    popover.appendChild(list);

    const actions = document.createElement("div");
    actions.className = "excel-filter-actions";
    const clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.className = "excel-filter-btn";
    clearBtn.textContent = "Clear filter";
    clearBtn.addEventListener("click", () => {
      for (const { cb } of rowRefs) cb.checked = true;
      delete state.columnFilters[colIndex];
      applyFilter(table);
      updateFilterButtonState(table, colIndex);
      closeFilterMenu(table);
    });
    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "excel-filter-btn excel-filter-btn--primary";
    closeBtn.textContent = "Close";
    closeBtn.addEventListener("click", () => closeFilterMenu(table));
    actions.appendChild(clearBtn);
    actions.appendChild(closeBtn);
    popover.appendChild(actions);

    positionPopover(popover, btn);
    state.openMenu = popover;
    syncSelectAll();

    state.menuOutsideHandler = (e) => {
      if (popover.contains(e.target) || btn.contains(e.target)) return;
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
      th.dataset.filterLabel = label;
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
      filterBtn.setAttribute("aria-haspopup", "dialog");
      filterBtn.innerHTML =
        '<svg class="col-filter-icon" width="10" height="10" viewBox="0 0 10 10" aria-hidden="true"><path fill="currentColor" d="M0 1h10L6 5v3L4 9V5L0 1z"/></svg>';

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
