(function () {
  "use strict";

  const STATUS_ORDER = ["open", "won", "lost", "push"];

  function inferType(raw) {
    const value = (raw || "").trim();
    if (!value) return { type: "text", value: "" };

    const pct = value.endsWith("%") ? value.slice(0, -1).replace(/^\+/, "") : value;
    const cleaned = pct.replace(/[₹,]/g, "").replace(/^\+/, "");
    const num = Number(cleaned);
    if (!Number.isNaN(num) && cleaned !== "") return { type: "number", value: num };

    // ISO / native parse
    const ts = Date.parse(value);
    if (!Number.isNaN(ts) && /[-T:]/.test(value)) return { type: "date", value: ts };

    // IST display format: DD/MM/YYYY HH:MM
    const m = value.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})(?:\s+(\d{1,2}):(\d{2}))?/);
    if (m) {
      const day = Number(m[1]);
      const month = Number(m[2]);
      const year = Number(m[3]);
      const hour = Number(m[4] || 0);
      const minute = Number(m[5] || 0);
      return { type: "date", value: Date.UTC(year, month - 1, day, hour, minute) };
    }

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

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function cellDateIso(raw) {
    const value = String(raw || "").trim();
    if (!value || value === "—") return null;
    const dmy = value.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
    if (dmy) return `${dmy[3]}-${pad2(dmy[2])}-${pad2(dmy[1])}`;
    const iso = value.match(/(\d{4})-(\d{2})-(\d{2})/);
    if (iso) return `${iso[1]}-${iso[2]}-${iso[3]}`;
    return null;
  }

  function isDateColumn(table, colIndex) {
    const th = table.tHead?.rows?.[0]?.cells?.[colIndex];
    if (!th) return false;
    const forced = String(th.dataset.filterType || "").toLowerCase();
    if (forced === "date") return true;
    if (forced === "list" || forced === "text" || forced === "number") return false;
    const label = (th.dataset.filterLabel || th.textContent || "").toLowerCase();
    if (/\bdate\b/.test(label)) return true;
    const values = collectColumnValues(table, colIndex).filter(Boolean);
    if (values.length < 2) return false;
    const dated = values.filter((v) => cellDateIso(v));
    return dated.length >= Math.ceil(values.length * 0.7);
  }

  function orderedDateRange(from, to) {
    if (!from) return { from: null, to: null };
    if (!to) return { from, to: from };
    return from <= to ? { from, to } : { from: to, to: from };
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

  function csvExportEnabled(table) {
    return table?.dataset.csvExport === "1";
  }

  function excelExportEnabled(table) {
    return table?.dataset.excelExport === "1";
  }

  function exportColumnIndexes(table) {
    const headers = Array.from(table.tHead?.rows?.[0]?.cells || []);
    const indexes = [];
    headers.forEach((th, idx) => {
      if (th.dataset.noExport === "1") return;
      if (th.dataset.noFilter === "1") return;
      indexes.push(idx);
    });
    return indexes;
  }

  /** @deprecated use exportColumnIndexes */
  function csvColumnIndexes(table) {
    return exportColumnIndexes(table);
  }

  function exportHeaderLabel(th) {
    const label =
      th?.dataset.filterLabel ||
      th?.querySelector(".th-label")?.textContent ||
      th?.textContent ||
      "";
    return String(label).trim();
  }

  function csvHeaderLabel(th) {
    return exportHeaderLabel(th);
  }

  function csvEscape(value) {
    const text = String(value ?? "");
    if (!/[",\n]/.test(text)) return text;
    return `"${text.replace(/"/g, '""')}"`;
  }

  function exportCellText(cell) {
    return String(cell?.textContent || "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function csvCellText(cell) {
    return exportCellText(cell);
  }

  function pathExportSlug() {
    return String(window.location?.pathname || "table")
      .replace(/^\/+|\/+$/g, "")
      .replace(/[^a-z0-9]+/gi, "-")
      .replace(/^-+|-+$/g, "")
      .toLowerCase();
  }

  function csvFilename(table) {
    const custom = String(table?.dataset.csvFilename || "").trim();
    if (custom) return `${custom}.csv`;
    return `${pathExportSlug() || "table"}-export.csv`;
  }

  function excelFilename(table) {
    const custom = String(
      table?.dataset.excelFilename || table?.dataset.csvFilename || ""
    ).trim();
    if (custom) return `${custom}.xlsx`;
    return `${pathExportSlug() || "table"}-export.xlsx`;
  }

  function collectVisibleExportMatrix(table) {
    const headers = Array.from(table.tHead?.rows?.[0]?.cells || []);
    const colIndexes = exportColumnIndexes(table);
    if (!headers.length || !colIndexes.length) return null;

    const matrix = [colIndexes.map((idx) => exportHeaderLabel(headers[idx]))];
    const rows = dataRows(table).filter((row) => row.style.display !== "none");
    for (const row of rows) {
      matrix.push(colIndexes.map((idx) => exportCellText(row.cells[idx])));
    }
    return matrix;
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function exportTableCsv(table) {
    const matrix = collectVisibleExportMatrix(table);
    if (!matrix) return;
    const lines = matrix.map((row) => row.map(csvEscape).join(","));
    const blob = new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
    downloadBlob(blob, csvFilename(table));
  }

  function xmlEscape(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function crc32Table() {
    if (crc32Table._t) return crc32Table._t;
    const table = new Uint32Array(256);
    for (let i = 0; i < 256; i += 1) {
      let c = i;
      for (let k = 0; k < 8; k += 1) {
        c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      }
      table[i] = c >>> 0;
    }
    crc32Table._t = table;
    return table;
  }

  function crc32(bytes) {
    let crc = 0xffffffff;
    const table = crc32Table();
    for (let i = 0; i < bytes.length; i += 1) {
      crc = table[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
    }
    return (crc ^ 0xffffffff) >>> 0;
  }

  function u16(n) {
    const b = new Uint8Array(2);
    new DataView(b.buffer).setUint16(0, n, true);
    return b;
  }

  function u32(n) {
    const b = new Uint8Array(4);
    new DataView(b.buffer).setUint32(0, n, true);
    return b;
  }

  function concatBytes(parts) {
    const total = parts.reduce((sum, p) => sum + p.length, 0);
    const out = new Uint8Array(total);
    let offset = 0;
    for (const part of parts) {
      out.set(part, offset);
      offset += part.length;
    }
    return out;
  }

  function encodeUtf8(text) {
    return new TextEncoder().encode(text);
  }

  /** Build a ZIP archive using STORE (no compression) — valid for .xlsx. */
  function zipStore(files) {
    const localParts = [];
    const centralParts = [];
    let offset = 0;

    for (const file of files) {
      const nameBytes = encodeUtf8(file.name);
      const data = file.data;
      const crc = crc32(data);
      const localHeader = concatBytes([
        u32(0x04034b50),
        u16(20),
        u16(0),
        u16(0),
        u16(0),
        u16(0),
        u32(crc),
        u32(data.length),
        u32(data.length),
        u16(nameBytes.length),
        u16(0),
        nameBytes,
      ]);
      localParts.push(localHeader, data);

      const centralHeader = concatBytes([
        u32(0x02014b50),
        u16(20),
        u16(20),
        u16(0),
        u16(0),
        u16(0),
        u16(0),
        u32(crc),
        u32(data.length),
        u32(data.length),
        u16(nameBytes.length),
        u16(0),
        u16(0),
        u16(0),
        u16(0),
        u32(0),
        u32(offset),
        nameBytes,
      ]);
      centralParts.push(centralHeader);
      offset += localHeader.length + data.length;
    }

    const centralDir = concatBytes(centralParts);
    const end = concatBytes([
      u32(0x06054b50),
      u16(0),
      u16(0),
      u16(files.length),
      u16(files.length),
      u32(centralDir.length),
      u32(offset),
      u16(0),
    ]);
    return concatBytes([...localParts, centralDir, end]);
  }

  function colName(index1Based) {
    let n = index1Based;
    let name = "";
    while (n > 0) {
      const rem = (n - 1) % 26;
      name = String.fromCharCode(65 + rem) + name;
      n = Math.floor((n - 1) / 26);
    }
    return name;
  }

  function buildSheetXml(matrix) {
    const rowCount = matrix.length;
    const colCount = matrix.reduce((max, row) => Math.max(max, row.length), 0);
    const lastCol = colName(Math.max(colCount, 1));
    const lastRow = Math.max(rowCount, 1);
    const rowsXml = matrix
      .map((row, rIdx) => {
        const cells = row
          .map((value, cIdx) => {
            const ref = `${colName(cIdx + 1)}${rIdx + 1}`;
            const text = xmlEscape(value);
            return `<c r="${ref}" t="inlineStr"><is><t>${text}</t></is></c>`;
          })
          .join("");
        return `<row r="${rIdx + 1}">${cells}</row>`;
      })
      .join("");
    return (
      `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
      `<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">` +
      `<dimension ref="A1:${lastCol}${lastRow}"/>` +
      `<sheetData>${rowsXml}</sheetData>` +
      `</worksheet>`
    );
  }

  function buildXlsxBytes(matrix) {
    const sheet = buildSheetXml(matrix);
    const contentTypes =
      `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
      `<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">` +
      `<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>` +
      `<Default Extension="xml" ContentType="application/xml"/>` +
      `<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>` +
      `<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>` +
      `</Types>`;
    const rels =
      `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
      `<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">` +
      `<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>` +
      `</Relationships>`;
    const workbook =
      `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
      `<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" ` +
      `xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">` +
      `<sheets><sheet name="Log" sheetId="1" r:id="rId1"/></sheets>` +
      `</workbook>`;
    const workbookRels =
      `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
      `<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">` +
      `<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>` +
      `</Relationships>`;
    return zipStore([
      { name: "[Content_Types].xml", data: encodeUtf8(contentTypes) },
      { name: "_rels/.rels", data: encodeUtf8(rels) },
      { name: "xl/workbook.xml", data: encodeUtf8(workbook) },
      { name: "xl/_rels/workbook.xml.rels", data: encodeUtf8(workbookRels) },
      { name: "xl/worksheets/sheet1.xml", data: encodeUtf8(sheet) },
    ]);
  }

  function exportTableExcel(table) {
    const matrix = collectVisibleExportMatrix(table);
    if (!matrix) return;
    const bytes = buildXlsxBytes(matrix);
    const blob = new Blob([bytes], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    downloadBlob(blob, excelFilename(table));
  }

  function buildExportCsvBtn(table) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "excel-filter-btn";
    btn.textContent = "Export CSV";
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      exportTableCsv(table);
      closeFilterMenu(table);
    });
    return btn;
  }

  function buildExportExcelBtn(table) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "excel-filter-btn";
    btn.textContent = "Export Excel";
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      exportTableExcel(table);
      closeFilterMenu(table);
    });
    return btn;
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
    if (!state) return;
    const filters = state.columnFilters || {};
    const dateFilters = state.columnDateFilters || {};
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
      if (show) {
        for (const [colKey, range] of Object.entries(dateFilters)) {
          if (!range || !range.from) continue;
          const colIndex = parseInt(colKey, 10);
          const { from, to } = orderedDateRange(range.from, range.to || range.from);
          const cellIso = cellDateIso(getFilterValue(row, colIndex, table));
          if (!cellIso || cellIso < from || cellIso > to) {
            show = false;
            break;
          }
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
    const dateRange = table._tableTools?.columnDateFilters?.[colIndex];
    if (dateRange?.from) return true;
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

  function openDateFilterMenu(table, colIndex, btn) {
    closeFilterMenu(table);
    const state = table._tableTools;
    const th = table.tHead?.rows?.[0]?.cells?.[colIndex];
    const colLabel =
      th?.dataset.filterLabel || th?.querySelector(".th-label")?.textContent || "Date";
    const existing = state.columnDateFilters[colIndex] || null;

    let draftFrom = existing?.from || null;
    let draftTo = existing?.to || existing?.from || null;
    let pickingEnd = false;
    let viewYear;
    let viewMonth;

    function initViewMonth() {
      const seed = draftTo || draftFrom;
      if (seed) {
        const [y, m] = seed.split("-").map(Number);
        viewYear = y;
        viewMonth = m - 1;
      } else {
        const now = new Date();
        viewYear = now.getFullYear();
        viewMonth = now.getMonth();
      }
    }

    initViewMonth();

    const popover = document.createElement("div");
    popover.className = "excel-filter-popover excel-filter-popover--date";
    popover.setAttribute("role", "dialog");
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
    sortAsc.textContent = "Sort oldest → newest";
    const sortDesc = document.createElement("button");
    sortDesc.type = "button";
    sortDesc.className = "excel-filter-link";
    sortDesc.textContent = "Sort newest → oldest";
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

    const nav = document.createElement("div");
    nav.className = "excel-cal__nav";
    const prevBtn = document.createElement("button");
    prevBtn.type = "button";
    prevBtn.className = "excel-cal__nav-btn";
    prevBtn.setAttribute("aria-label", "Previous month");
    prevBtn.textContent = "‹";
    const monthLabel = document.createElement("div");
    monthLabel.className = "excel-cal__month";
    const nextBtn = document.createElement("button");
    nextBtn.type = "button";
    nextBtn.className = "excel-cal__nav-btn";
    nextBtn.setAttribute("aria-label", "Next month");
    nextBtn.textContent = "›";
    nav.appendChild(prevBtn);
    nav.appendChild(monthLabel);
    nav.appendChild(nextBtn);
    popover.appendChild(nav);

    const weekdays = document.createElement("div");
    weekdays.className = "excel-cal__weekdays";
    weekdays.setAttribute("aria-hidden", "true");
    for (const day of ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]) {
      const span = document.createElement("span");
      span.textContent = day;
      weekdays.appendChild(span);
    }
    popover.appendChild(weekdays);

    const grid = document.createElement("div");
    grid.className = "excel-cal__grid";
    grid.setAttribute("role", "grid");
    popover.appendChild(grid);

    const hint = document.createElement("p");
    hint.className = "excel-cal__hint";
    popover.appendChild(hint);

    function updateHint() {
      const { from, to } = orderedDateRange(draftFrom, draftTo);
      if (!from) {
        hint.textContent = "Click a day, or click two days for a range.";
      } else if (pickingEnd && from === to) {
        hint.textContent = `Selected ${from}. Click another day to extend, or Apply.`;
      } else if (from === to) {
        hint.textContent = `Single day: ${from}`;
      } else {
        hint.textContent = `Range: ${from} → ${to}`;
      }
    }

    function renderCalendar() {
      const monthNames = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
      ];
      monthLabel.textContent = `${monthNames[viewMonth]} ${viewYear}`;
      const first = new Date(viewYear, viewMonth, 1);
      const startPad = (first.getDay() + 6) % 7;
      const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
      const prevDays = new Date(viewYear, viewMonth, 0).getDate();
      const { from, to } = orderedDateRange(draftFrom, draftTo);
      const today = new Date();
      const todayIso = `${today.getFullYear()}-${pad2(today.getMonth() + 1)}-${pad2(today.getDate())}`;
      grid.innerHTML = "";

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
        const iso = `${y}-${pad2(m + 1)}-${pad2(day)}`;
        const btnDay = document.createElement("button");
        btnDay.type = "button";
        btnDay.className = "excel-cal__day";
        btnDay.dataset.date = iso;
        btnDay.textContent = String(day);
        if (outside) {
          btnDay.classList.add("is-outside");
          btnDay.tabIndex = -1;
        }
        if (iso === todayIso) btnDay.classList.add("is-today");
        if (from && to && iso >= from && iso <= to) btnDay.classList.add("is-in-range");
        if (from && iso === from) btnDay.classList.add("is-range-start", "is-selected");
        if (to && iso === to) btnDay.classList.add("is-range-end", "is-selected");
        btnDay.addEventListener("click", () => {
          if (!draftFrom || !pickingEnd) {
            draftFrom = iso;
            draftTo = iso;
            pickingEnd = true;
          } else {
            draftTo = iso;
            pickingEnd = false;
          }
          renderCalendar();
        });
        grid.appendChild(btnDay);
      }
      updateHint();
    }

    prevBtn.addEventListener("click", () => {
      viewMonth -= 1;
      if (viewMonth < 0) {
        viewMonth = 11;
        viewYear -= 1;
      }
      renderCalendar();
    });
    nextBtn.addEventListener("click", () => {
      viewMonth += 1;
      if (viewMonth > 11) {
        viewMonth = 0;
        viewYear += 1;
      }
      renderCalendar();
    });

    const actions = document.createElement("div");
    actions.className = "excel-filter-actions";
    if (csvExportEnabled(table)) {
      actions.appendChild(buildExportCsvBtn(table));
    }
    if (excelExportEnabled(table)) {
      actions.appendChild(buildExportExcelBtn(table));
    }
    const clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.className = "excel-filter-btn";
    clearBtn.textContent = "Clear";
    clearBtn.addEventListener("click", () => {
      delete state.columnDateFilters[colIndex];
      draftFrom = null;
      draftTo = null;
      pickingEnd = false;
      applyFilter(table);
      updateFilterButtonState(table, colIndex);
      renderCalendar();
    });
    const applyBtn = document.createElement("button");
    applyBtn.type = "button";
    applyBtn.className = "excel-filter-btn excel-filter-btn--primary";
    applyBtn.textContent = "Apply";
    applyBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const { from, to } = orderedDateRange(draftFrom, draftTo);
      if (!from) delete state.columnDateFilters[colIndex];
      else state.columnDateFilters[colIndex] = { from, to };
      delete state.columnFilters[colIndex];
      applyFilter(table);
      updateFilterButtonState(table, colIndex);
      closeFilterMenu(table);
    });
    actions.appendChild(clearBtn);
    actions.appendChild(applyBtn);
    popover.appendChild(actions);

    positionPopover(popover, btn);
    state.openMenu = popover;
    renderCalendar();

    state.menuOutsideHandler = (e) => {
      if (popover.contains(e.target) || btn.contains(e.target)) return;
      closeFilterMenu(table);
    };
    setTimeout(() => document.addEventListener("click", state.menuOutsideHandler), 0);
  }

  function openFilterMenu(table, colIndex, btn) {
    if (isDateColumn(table, colIndex)) {
      openDateFilterMenu(table, colIndex, btn);
      return;
    }
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
    if (csvExportEnabled(table)) {
      actions.appendChild(buildExportCsvBtn(table));
    }
    if (excelExportEnabled(table)) {
      actions.appendChild(buildExportExcelBtn(table));
    }
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
      if (th.dataset.noFilter === "1") {
        th.classList.add("th-nofilter");
        return;
      }
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

  function attachExportToolbar(table) {
    const wantCsv = csvExportEnabled(table);
    const wantExcel = excelExportEnabled(table);
    if (!wantCsv && !wantExcel) return;
    if (table.dataset.exportToolbarAttached === "1") return;
    table.dataset.exportToolbarAttached = "1";

    const bar = document.createElement("div");
    bar.className = "table-tools table-export-bar";
    if (wantCsv) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn-secondary";
      btn.textContent = "Export CSV";
      btn.setAttribute("aria-label", "Download visible rows as CSV");
      btn.addEventListener("click", () => exportTableCsv(table));
      bar.appendChild(btn);
    }
    if (wantExcel) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn-secondary";
      btn.textContent = "Export Excel";
      btn.setAttribute("aria-label", "Download visible rows as Excel workbook");
      btn.addEventListener("click", () => exportTableExcel(table));
      bar.appendChild(btn);
    }
    table.parentNode.insertBefore(bar, table);
  }

  /** @deprecated use attachExportToolbar */
  function attachCsvExportToolbar(table) {
    attachExportToolbar(table);
  }

  function enhanceWithColumnFilters(table) {
    table.classList.add("sortable-filterable", "column-filterable");
    table._tableTools = {
      sortIndex: -1,
      direction: "asc",
      columnFilters: {},
      columnDateFilters: {},
      openMenu: null,
      openCol: -1,
      menuOutsideHandler: null,
    };
    buildColumnHeaders(table);
    attachExportToolbar(table);
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

  window.TableTools = {
    enhanceTable,
    enhanceAll,
    reapply,
    closeFilterMenu,
    exportTableCsv,
    exportTableExcel,
  };
})();
