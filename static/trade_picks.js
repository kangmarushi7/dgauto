(function () {
  "use strict";

  const categoryFilter = document.getElementById("categoryFilter");
  const strategyFilter = document.getElementById("strategyFilter");
  const includeSettled = document.getElementById("includeSettled");
  const exportCsv = document.getElementById("exportCsv");
  const table = document.getElementById("tradePicksTable");
  const kpiShown = document.getElementById("kpiShown");

  function syncExportHref() {
    if (!exportCsv) return;
    const params = new URLSearchParams();
    if (includeSettled && includeSettled.checked) params.set("include_settled", "1");
    if (categoryFilter && categoryFilter.value) params.set("category", categoryFilter.value);
    if (strategyFilter && strategyFilter.value) params.set("strategy", strategyFilter.value);
    const q = params.toString();
    exportCsv.href = "/api/trade-picks/export" + (q ? "?" + q : "");
  }

  function applyClientFilters() {
    if (!table) return;
    const cat = (categoryFilter && categoryFilter.value) || "";
    const strat = (strategyFilter && strategyFilter.value) || "";
    let shown = 0;
    for (const row of table.tBodies[0]?.rows || []) {
      const matchCat = !cat || row.dataset.category === cat;
      const matchStrat = !strat || row.dataset.strategy === strat ||
        (strat === "arahus" && String(row.dataset.strategy || "").startsWith("arahus"));
      const visible = matchCat && matchStrat;
      row.hidden = !visible;
      if (visible) shown += 1;
    }
    if (kpiShown) kpiShown.textContent = String(shown);
    syncExportHref();
  }

  if (categoryFilter) categoryFilter.addEventListener("change", applyClientFilters);
  if (strategyFilter) strategyFilter.addEventListener("change", applyClientFilters);

  if (includeSettled) {
    includeSettled.addEventListener("change", () => {
      const params = new URLSearchParams(window.location.search);
      if (includeSettled.checked) params.set("include_settled", "1");
      else params.delete("include_settled");
      const q = params.toString();
      window.location.search = q ? "?" + q : "";
    });
  }

  syncExportHref();
  applyClientFilters();
})();
