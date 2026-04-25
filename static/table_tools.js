(function () {
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

  function applyFilter(table) {
    const state = table._tableTools;
    if (!state) return;
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
      h.classList.remove("sort-asc", "sort-desc");
      if (idx === state.sortIndex) {
        h.classList.add(state.direction === "asc" ? "sort-asc" : "sort-desc");
      }
    });
  }

  function enhanceTable(table) {
    if (!table || table.dataset.tableEnhanced === "1") return;
    if (!table.tHead || !table.tBodies.length) return;

    table.dataset.tableEnhanced = "1";
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

  function enhanceAll() {
    const tables = Array.from(document.querySelectorAll("table"));
    tables.forEach(enhanceTable);
  }

  function reapply(table) {
    if (!table || !table._tableTools) return;
    applySort(table);
    applyFilter(table);
    markHeaderSort(table);
  }

  window.TableTools = { enhanceTable, enhanceAll, reapply };
})();
