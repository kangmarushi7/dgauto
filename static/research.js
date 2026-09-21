(() => {
  const state = {
    slice: "combined",
    payload: null,
    status: "never_run",
    buckets: null,
  };

  const el = {
    refreshBtn: document.getElementById("refreshBtn"),
    bucketsBtn: document.getElementById("bucketsBtn"),
    statusText: document.getElementById("statusText"),
    metaLine: document.getElementById("metaLine"),
    emptyState: document.getElementById("emptyState"),
    root: document.getElementById("researchRoot"),
    summary: document.getElementById("summaryCards"),
    markets: document.getElementById("marketsTable"),
    odds: document.getElementById("oddsTable"),
    leagues: document.getElementById("leaguesTable"),
    rolling: document.getElementById("rollingTable"),
    focusSection: document.getElementById("focusSection"),
    focusBlocks: document.getElementById("focusBlocks"),
    keepList: document.getElementById("keepList"),
    cutList: document.getElementById("cutList"),
    consensus: document.getElementById("consensusBlock"),
    dlMd: document.getElementById("dlMd"),
    dlPdf: document.getElementById("dlPdf"),
    bucketsMeta: document.getElementById("bucketsMeta"),
    bucketsLiveSummary: document.getElementById("bucketsLiveSummary"),
    bucketsTable: document.getElementById("bucketsTable"),
  };

  function fmt(n, digits = 1) {
    if (n == null || Number.isNaN(n)) return "—";
    const sign = n > 0 ? "+" : "";
    return sign + Number(n).toFixed(digits);
  }

  function toneClass(n) {
    if (n == null || Number.isNaN(n) || n === 0) return "";
    return n > 0 ? "is-pos" : "is-neg";
  }

  function setExports(exports) {
    const md = !!(exports && exports.md);
    const pdf = !!(exports && exports.pdf);
    el.dlMd.classList.toggle("is-disabled", !md);
    el.dlPdf.classList.toggle("is-disabled", !pdf);
  }

  function setStatus(status, generatedAt, error, elapsed) {
    state.status = status;
    const running = status === "running";
    el.refreshBtn.disabled = running;
    let text = "Unknown";
    if (status === "never_run") text = "Never run — refresh to analyze";
    else if (status === "ready") text = "Ready";
    else if (status === "running") text = "Running analysis…";
    else if (status === "error") text = `Error: ${error || "refresh failed"}`;
    el.statusText.textContent = text;
    const bits = [];
    if (generatedAt) bits.push(`Last run: ${generatedAt}`);
    if (elapsed != null) bits.push(`took ${elapsed}s`);
    el.metaLine.textContent = bits.join(" · ");
  }

  function renderAggTable(rows, keyHeader) {
    if (!rows || !rows.length) return "<p class='research-meta'>No rows.</p>";
    const body = rows
      .map((r) => {
        const pnlCls = toneClass(r.pnl_units);
        const roiCls = toneClass(r.roi_pct);
        return `<tr>
          <td>${escapeHtml(r.key)}</td>
          <td>${r.n}</td>
          <td>${r.win_pct != null ? r.win_pct.toFixed(1) : "—"}</td>
          <td class="${pnlCls}">${fmt(r.pnl_units)}</td>
          <td class="${roiCls}">${r.roi_pct != null ? fmt(r.roi_pct) + "%" : "—"}</td>
          <td>${r.avg_odds != null ? r.avg_odds.toFixed(3) : "—"}</td>
        </tr>`;
      })
      .join("");
    return `<table class="research-table">
      <thead><tr>
        <th>${escapeHtml(keyHeader)}</th><th>N</th><th>Win%</th><th>PnL(u)</th><th>ROI%</th><th>Avg odds</th>
      </tr></thead>
      <tbody>${body}</tbody>
    </table>`;
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function stateClass(st) {
    const s = String(st || "").toUpperCase();
    if (s === "LIVE") return "is-live";
    if (s === "TRACKING") return "is-tracking";
    return "is-logging";
  }

  function fmtRoiFrac(roi) {
    if (roi == null || Number.isNaN(roi)) return "—";
    return fmt(roi * 100) + "%";
  }

  function gateSummary(gates) {
    if (!gates) return "—";
    const labels = [
      ["a_sample_size", "n"],
      ["b_positive_months", "MoM+"],
      ["c_full_roi_ge_5pct", "ROI≥5%"],
      ["d_no_monotone_decline", "trend"],
    ];
    return labels
      .map(([k, label]) => {
        const ok = !!gates[k];
        return `<span class="${ok ? "bucket-gates-pass" : "bucket-gates-fail"}">${label}${
          ok ? "✓" : "✗"
        }</span>`;
      })
      .join(" ");
  }

  async function loadBuckets() {
    if (el.bucketsBtn) el.bucketsBtn.disabled = true;
    // Don't wipe SSR content with "Loading…" unless the table is empty.
    if (el.bucketsMeta && !(el.bucketsTable && el.bucketsTable.querySelector("table"))) {
      el.bucketsMeta.textContent = "Loading bucket status…";
    }
    try {
      const res = await fetch("/api/strategy-buckets/status");
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || res.statusText);
      state.buckets = body;
      renderBuckets(body);
    } catch (err) {
      state.buckets = null;
      renderBuckets({ error: String(err) });
    } finally {
      if (el.bucketsBtn) el.bucketsBtn.disabled = false;
    }
  }

  function renderBuckets(payload) {
    if (!el.bucketsTable || !el.bucketsMeta) return;
    try {
      if (!payload || payload.error) {
        el.bucketsMeta.textContent = payload?.error
          ? `Buckets error: ${payload.error}`
          : "No bucket data.";
        el.bucketsTable.innerHTML = "";
        if (el.bucketsLiveSummary) el.bucketsLiveSummary.innerHTML = "";
        return;
      }

      const cats = payload.categories || {};
      const ids = Object.keys(cats);
      const stake = payload.flat_stake_usd != null ? Number(payload.flat_stake_usd).toFixed(2) : "1.00";
      el.bucketsMeta.textContent = `Flat stake $${stake} · ${ids.length} categories · generated ${
        payload.generated_at || "—"
      }`;

      const liveCats = ids.filter((id) => String(cats[id].state).toUpperCase() === "LIVE");
      const liveN = liveCats.reduce((s, id) => s + (cats[id].n || 0), 0);
      const liveRoi =
        liveN > 0
          ? liveCats.reduce((s, id) => s + (Number(cats[id].roi_full) || 0) * (cats[id].n || 0), 0) /
            liveN
          : null;

      if (el.bucketsLiveSummary) {
        el.bucketsLiveSummary.innerHTML = [
          ["LIVE categories", String(liveCats.length), ""],
          ["LIVE settled n", String(liveN), ""],
          [
            "LIVE ROI (weighted)",
            liveRoi != null ? fmtRoiFrac(liveRoi) : "—",
            toneClass(liveRoi != null ? liveRoi * 100 : null),
          ],
          ["Stake", `$${stake}`, ""],
        ]
          .map(
            ([label, value, cls]) =>
              `<article class="research-stat">
            <p class="research-stat__label">${label}</p>
            <p class="research-stat__value ${cls}">${value}</p>
          </article>`
          )
          .join("");
      }

      const order = { LIVE: 0, TRACKING: 1, LOGGING: 2 };
      const sorted = ids.slice().sort((a, b) => {
        const sa = String(cats[a].state || "").toUpperCase();
        const sb = String(cats[b].state || "").toUpperCase();
        return (order[sa] ?? 9) - (order[sb] ?? 9) || a.localeCompare(b);
      });

      const body = sorted
        .map((id) => {
          const c = cats[id];
          const st = String(c.state || "").toUpperCase();
          const mom = (c.roi_last_3_months || [])
            .map((m) => `${m.month}:${m.roi != null ? fmt(m.roi * 100) + "%" : "—"}`)
            .join(" · ");
          const gatesPass = c.graduation_all_pass;
          return `<tr>
          <td>${escapeHtml(id)}</td>
          <td><span class="bucket-state ${stateClass(st)}">${escapeHtml(st)}</span></td>
          <td>${c.n ?? 0}</td>
          <td class="${toneClass(c.roi_full != null ? c.roi_full * 100 : null)}">${fmtRoiFrac(
            c.roi_full
          )}</td>
          <td>${escapeHtml(mom || "—")}</td>
          <td class="${gatesPass ? "bucket-gates-pass" : "bucket-gates-fail"}">${
            gatesPass ? "PASS" : "fail"
          }</td>
          <td>${gateSummary(c.graduation_gates)}</td>
          <td>$${Number(c.stake_usd || 0).toFixed(2)}</td>
        </tr>`;
        })
        .join("");

      el.bucketsTable.innerHTML = `<table class="research-table">
      <thead><tr>
        <th>Category</th><th>State</th><th>N</th><th>ROI</th><th>Last 3 mo</th><th>Gates</th><th>a–d</th><th>Stake</th>
      </tr></thead>
      <tbody>${body}</tbody>
    </table>`;
    } catch (err) {
      el.bucketsMeta.textContent = `Buckets render error: ${err}`;
    }
  }

  function currentSlice() {
    const data = state.payload;
    if (!data || !data.slices) return null;
    return data.slices[state.slice] || null;
  }

  function render() {
    const data = state.payload;
    if (!data) {
      el.root.hidden = true;
      el.emptyState.hidden = false;
      return;
    }
    el.emptyState.hidden = true;
    el.root.hidden = false;
    const sl = currentSlice();
    if (!sl) return;

    const o = sl.overall || {};
    el.summary.innerHTML = [
      ["Settled", String(o.n ?? "—"), ""],
      ["Win %", o.win_pct != null ? o.win_pct.toFixed(1) + "%" : "—", ""],
      ["PnL (u)", fmt(o.pnl_units), toneClass(o.pnl_units)],
      ["ROI", o.roi_pct != null ? fmt(o.roi_pct) + "%" : "—", toneClass(o.roi_pct)],
    ]
      .map(
        ([label, value, cls]) =>
          `<article class="research-stat">
            <p class="research-stat__label">${label}</p>
            <p class="research-stat__value ${cls}">${value}</p>
          </article>`
      )
      .join("");

    el.markets.innerHTML = renderAggTable(sl.by_market, "Market");
    el.odds.innerHTML = renderAggTable(sl.by_odds, "Odds");
    el.leagues.innerHTML = renderAggTable(sl.by_league_volume, "League");

    const rollingRows = [25, 50, 100].map((d) => {
      const a = (sl.rolling && sl.rolling[`${d}d`]) || {};
      return {
        key: `last ${d}d`,
        n: a.n,
        win_pct: a.win_pct,
        pnl_units: a.pnl_units,
        roi_pct: a.roi_pct,
        avg_odds: a.avg_odds,
      };
    });
    el.rolling.innerHTML = renderAggTable(rollingRows, "Window");

    const focus = sl.market_odds || [];
    if (focus.length) {
      el.focusSection.hidden = false;
      el.focusBlocks.innerHTML = focus
        .map((block) => {
          const overall = block.overall || {};
          return `<div class="research-focus-block">
            <h3>${escapeHtml(block.market)}
              <span class="research-meta">n=${overall.n ?? 0} · PnL ${fmt(overall.pnl_units)} · ROI ${
                overall.roi_pct != null ? fmt(overall.roi_pct) + "%" : "—"
              }</span>
            </h3>
            <div class="research-table-wrap">${renderAggTable(block.by_odds, "Odds")}</div>
          </div>`;
        })
        .join("");
    } else {
      el.focusSection.hidden = true;
      el.focusBlocks.innerHTML = "";
    }

    let keep = [];
    let cut = [];
    if (state.slice === "combined") {
      keep = data.playbook_keep || [];
      cut = data.playbook_cut || [];
    } else {
      keep = (sl.keep || []).map((x) => ({ ...x, strategy: sl.label }));
      cut = (sl.cut || []).map((x) => ({ ...x, strategy: sl.label }));
    }

    el.keepList.innerHTML = keep.length
      ? keep
          .map((item) => {
            if (item.detail) {
              return `<li><strong>${escapeHtml(item.scope)}</strong> (${escapeHtml(
                item.strategy || ""
              )}): ${escapeHtml(item.detail)}</li>`;
            }
            return `<li><strong>${escapeHtml(item.scope)}</strong> (${escapeHtml(
              item.strategy || ""
            )}): n=${item.n ?? "—"}, ROI ${
              item.roi_pct != null ? fmt(item.roi_pct) + "%" : "—"
            }, PnL ${fmt(item.pnl_units)}</li>`;
          })
          .join("")
      : "<li>None at current thresholds.</li>";

    el.cutList.innerHTML = cut.length
      ? cut
          .map(
            (item) =>
              `<li><strong>${escapeHtml(item.scope)}</strong> (${escapeHtml(
                item.strategy || ""
              )}): n=${item.n ?? "—"}, ROI ${
                item.roi_pct != null ? fmt(item.roi_pct) + "%" : "—"
              }, PnL ${fmt(item.pnl_units)}</li>`
          )
          .join("")
      : "<li>None at current thresholds.</li>";

    const cons = data.consensus || [];
    if (state.slice === "combined" && cons.length) {
      el.consensus.innerHTML =
        `<h3>Cross-strategy durable angles</h3><ul>` +
        cons
          .map(
            (c) =>
              `<li><strong>${escapeHtml(c.angle)}</strong> (${escapeHtml(
                c.strategies
              )}): ${escapeHtml(c.detail)}</li>`
          )
          .join("") +
        `</ul>`;
    } else {
      el.consensus.innerHTML = "";
    }

    // Prefer fresh buckets API; fall back to research payload embed.
    if (!state.buckets && data.live_buckets) {
      renderBuckets(data.live_buckets);
    }
  }

  async function loadCached() {
    const res = await fetch("/api/research");
    const body = await res.json();
    state.payload = body.data || null;
    setStatus(body.status, body.generated_at, body.error, body.elapsed_sec);
    setExports(body.exports);
    render();
  }

  async function refresh() {
    setStatus("running");
    el.refreshBtn.disabled = true;
    try {
      const res = await fetch("/api/research/refresh", { method: "POST" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setStatus("error", null, body.detail || res.statusText);
        await loadCached();
        return;
      }
      state.payload = body.data || null;
      setStatus("ready", body.generated_at, null, body.elapsed_sec);
      setExports(body.exports);
      render();
      await loadBuckets();
    } catch (err) {
      setStatus("error", null, String(err));
      await loadCached();
    } finally {
      el.refreshBtn.disabled = state.status === "running";
    }
  }

  document.querySelectorAll(".research-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".research-tab").forEach((b) => {
        b.classList.toggle("is-active", b === btn);
        b.setAttribute("aria-selected", b === btn ? "true" : "false");
      });
      state.slice = btn.dataset.slice;
      render();
    });
  });

  el.refreshBtn.addEventListener("click", refresh);
  if (el.bucketsBtn) el.bucketsBtn.addEventListener("click", loadBuckets);

  // Buckets first (fast), then profitability cache — avoids a stuck "Loading…" race.
  loadBuckets()
    .catch((err) => renderBuckets({ error: String(err) }))
    .finally(() => {
      loadCached().catch((err) => setStatus("error", null, String(err)));
    });
})();
