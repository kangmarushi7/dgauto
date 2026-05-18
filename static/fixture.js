(function () {
  function drawRadar() {
    const el = document.getElementById("teamRadar");
    const dataEl = document.getElementById("radarData");
    if (!el || !dataEl) return;

    let axes;
    try {
      axes = JSON.parse(dataEl.textContent || "[]");
    } catch {
      return;
    }
    if (!axes.length) return;

    const ctx = el.getContext("2d");
    const w = el.width;
    const h = el.height;
    const cx = w / 2;
    const cy = h / 2;
    const r = Math.min(w, h) * 0.36;
    const n = axes.length;

    ctx.clearRect(0, 0, w, h);

    ctx.strokeStyle = "rgba(255,255,255,0.08)";
    for (let ring = 1; ring <= 4; ring++) {
      ctx.beginPath();
      const rr = (r * ring) / 4;
      for (let i = 0; i < n; i++) {
        const a = (Math.PI * 2 * i) / n - Math.PI / 2;
        const x = cx + rr * Math.cos(a);
        const y = cy + rr * Math.sin(a);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.stroke();
    }

    function poly(values, color, fillAlpha) {
      ctx.beginPath();
      for (let i = 0; i < n; i++) {
        const a = (Math.PI * 2 * i) / n - Math.PI / 2;
        const v = Math.min(100, Math.max(0, values[i] || 0)) / 100;
        const x = cx + r * v * Math.cos(a);
        const y = cy + r * v * Math.sin(a);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.fillStyle = color.replace("1)", fillAlpha + ")");
      ctx.fill();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    poly(
      axes.map((a) => a.away),
      "rgba(167, 139, 250, 1)",
      0.12
    );
    poly(
      axes.map((a) => a.home),
      "rgba(59, 158, 255, 1)",
      0.15
    );

    ctx.fillStyle = "#8b9cb3";
    ctx.font = "10px IBM Plex Sans, sans-serif";
    axes.forEach((ax, i) => {
      const a = (Math.PI * 2 * i) / n - Math.PI / 2;
      const x = cx + (r + 18) * Math.cos(a);
      const y = cy + (r + 18) * Math.sin(a);
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(ax.axis, x, y);
    });
  }

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

  function boot() {
    drawRadar();
    renderHeatmap();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
