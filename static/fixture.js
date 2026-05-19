(function () {
  "use strict";

  function renderHeatmap() {
    const root = document.querySelector(".mini-heatmap");
    if (!root) return;
    let matrix;
    try {
      matrix = JSON.parse(root.getAttribute("data-matrix") || "[]");
    } catch {
      return;
    }
    if (!matrix.length) return;

    const maxPct = Math.max(
      ...matrix.flatMap((row) => row.map((c) => c.pct || 0)),
      1
    );

    matrix.forEach((row) => {
      const rowEl = document.createElement("div");
      rowEl.style.display = "grid";
      rowEl.style.gridTemplateColumns = `repeat(${row.length}, 1fr)`;
      rowEl.style.gap = "2px";
      rowEl.style.marginBottom = "2px";
      row.forEach((cell) => {
        const cellEl = document.createElement("div");
        const intensity = (cell.pct || 0) / maxPct;
        const g = Math.round(80 + intensity * 120);
        cellEl.style.background = `rgba(0, ${g}, ${Math.round(g * 0.7)}, ${0.15 + intensity * 0.65})`;
        cellEl.style.padding = "4px";
        cellEl.style.textAlign = "center";
        cellEl.style.borderRadius = "3px";
        cellEl.style.fontSize = "0.65rem";
        cellEl.textContent = cell.pct ? cell.pct.toFixed(1) : "";
        cellEl.title = `${cell.home}-${cell.away}`;
        rowEl.appendChild(cellEl);
      });
      root.appendChild(rowEl);
    });
  }

  function renderTimeline() {
    const root = document.getElementById("flowTimeline");
    if (!root) return;
    let segs;
    try {
      const el = document.getElementById("timelineData");
      segs = JSON.parse(el?.textContent || "[]");
    } catch {
      return;
    }
    if (!segs.length) return;

    const wrap = document.createElement("div");
    wrap.className = "timeline-wrap";

    const axis = document.createElement("div");
    axis.className = "timeline-axis";
    axis.innerHTML = "<span>0'</span><span>HT</span><span>90'</span>";
    wrap.appendChild(axis);

    const track = document.createElement("div");
    track.className = "timeline-track";
    segs.forEach((s) => {
      const seg = document.createElement("div");
      seg.className = "timeline-seg";
      seg.style.flex = String(s.pressure || 25);
      const fill = document.createElement("div");
      fill.className = "timeline-fill";
      fill.style.height = `${Math.min(100, s.pressure || 20)}%`;
      fill.title = `${s.label}: ${s.pressure}% pressure`;
      seg.appendChild(fill);
      const lbl = document.createElement("span");
      lbl.className = "timeline-lbl";
      lbl.textContent = s.label;
      seg.appendChild(lbl);
      track.appendChild(seg);
    });
    wrap.appendChild(track);
    root.appendChild(wrap);
  }

  function renderDistributions() {
    const root = document.getElementById("distGrid");
    if (!root) return;
    let data;
    try {
      const el = document.getElementById("distData");
      data = JSON.parse(el?.textContent || "{}");
    } catch {
      return;
    }

    const labels = {
      goals: "Goals (total)",
      corners: "Corners",
      shots: "Shots",
      cards: "Cards",
    };

    Object.entries(labels).forEach(([key, title]) => {
      const buckets = data[key];
      if (!buckets || !buckets.length) return;
      const card = document.createElement("article");
      card.className = "dist-card";
      const h = document.createElement("h3");
      h.textContent = title;
      card.appendChild(h);
      const chart = document.createElement("div");
      chart.className = "dist-chart";
      buckets.slice(0, 14).forEach((b) => {
        const col = document.createElement("div");
        col.className = "dist-col";
        const bar = document.createElement("div");
        bar.className = "dist-bar";
        bar.style.height = `${b.bar_width || 10}%`;
        col.appendChild(bar);
        const lab = document.createElement("span");
        lab.textContent = b.label;
        col.appendChild(lab);
        chart.appendChild(col);
      });
      card.appendChild(chart);
      root.appendChild(card);
    });
  }

  function boot() {
    renderHeatmap();
    renderTimeline();
    renderDistributions();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
