(() => {
  "use strict";

  // ── Presets ───────────────────────────────────────────────────────────────
  const DTE_PRESETS = {
    WEEKLY:    { min: 1,   max: 7,   label: "1–7 DTE" },
    MONTHLY:   { min: 21,  max: 35,  label: "21–35 DTE" },
    STANDARD:  { min: 38,  max: 52,  label: "38–52 DTE" },
    QUARTERLY: { min: 60,  max: 90,  label: "60–90 DTE" },
    LEAPS:     { min: 180, max: 730, label: "180–730 DTE" },
    CUSTOM:    { min: 1,   max: 730, label: "Custom DTE" },
  };

  // ── State ─────────────────────────────────────────────────────────────────
  let allRows       = [];
  let filteredRows  = [];
  let currentTab    = "all";
  let sortCol       = "realistic_yield";
  let sortDir       = "desc";
  let colsExpanded  = false;
  let activePreset  = "STANDARD";
  let scanPollTimer = null;

  // ── DOM refs ──────────────────────────────────────────────────────────────
  const $ = id => document.getElementById(id);

  // ── Account size (localStorage) ───────────────────────────────────────────
  function getAccountSize() {
    return parseFloat($("account-size-input").value) || 0;
  }
  function loadAccountSize() {
    const v = localStorage.getItem("csp_account_size");
    if (v) $("account-size-input").value = v;
  }
  function saveAccountSize() {
    localStorage.setItem("csp_account_size", $("account-size-input").value);
  }

  // ── DTE preset logic ──────────────────────────────────────────────────────
  function setPreset(name) {
    // When switching TO Custom, seed the inputs from the currently active preset
    if (name === "CUSTOM" && activePreset !== "CUSTOM") {
      const prev = DTE_PRESETS[activePreset];
      $("dte-min-input").value = prev.min;
      $("dte-max-input").value = prev.max;
      $("dte-badge").textContent = `${prev.min}–${prev.max} DTE`;
    }

    activePreset = name;
    document.querySelectorAll(".btn-dte").forEach(b => {
      b.classList.toggle("active", b.dataset.preset === name);
    });
    const custom = $("dte-custom");
    if (name === "CUSTOM") {
      custom.classList.remove("hidden");
    } else {
      custom.classList.add("hidden");
      const p = DTE_PRESETS[name];
      $("dte-min-input").value = p.min;
      $("dte-max-input").value = p.max;
      $("dte-badge").textContent = p.label;
    }
  }

  function getDteRange() {
    if (activePreset !== "CUSTOM") {
      const p = DTE_PRESETS[activePreset];
      return { min: p.min, max: p.max };
    }
    return {
      min: parseInt($("dte-min-input").value) || 1,
      max: parseInt($("dte-max-input").value) || 730,
    };
  }

  // ── Scan ──────────────────────────────────────────────────────────────────
  function startScan() {
    const { min, max } = getDteRange();
    if (min > max) {
      showError("Min DTE must be less than Max DTE.");
      return;
    }
    const btn = $("run-scan-btn");
    btn.disabled = true;
    $("scan-banner").classList.remove("hidden");
    $("scan-banner-text").textContent = "Scan in progress…";
    $("scan-progress-fill").style.width = "5%";
    $("success-banner").classList.add("hidden");
    $("error-banner").classList.add("hidden");

    fetch("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ preset: activePreset, dte_min: min, dte_max: max }),
    })
      .then(r => r.json())
      .then(d => {
        if (d.error) throw new Error(d.error);
        pollScanStatus();
      })
      .catch(err => {
        showError("Failed to start scan: " + err.message);
        $("scan-banner").classList.add("hidden");
        btn.disabled = false;
      });
  }

  function pollScanStatus() {
    if (scanPollTimer) clearInterval(scanPollTimer);
    let fakeProgress = 10;
    scanPollTimer = setInterval(() => {
      fakeProgress = Math.min(fakeProgress + 3, 90);
      $("scan-progress-fill").style.width = fakeProgress + "%";

      fetch("/api/scan/status")
        .then(r => r.json())
        .then(s => {
          if (!s.running) {
            clearInterval(scanPollTimer);
            scanPollTimer = null;
            $("scan-progress-fill").style.width = "100%";
            setTimeout(() => {
              $("scan-banner").classList.add("hidden");
              $("run-scan-btn").disabled = false;
              if (s.error) {
                showError("Scan failed: " + s.error);
              } else {
                loadLatestResults();
              }
            }, 400);
          }
        })
        .catch(() => {});
    }, 2000);
  }

  // ── Load results ──────────────────────────────────────────────────────────
  function syncSidebarDte(data) {
    const dMin = data.summary?.dte_min;
    const dMax = data.summary?.dte_max;
    if (dMin != null) $("filter-dte-min").value = dMin;
    if (dMax != null) $("filter-dte-max").value = dMax;
  }

  function loadLatestResults() {
    fetch("/api/results/latest")
      .then(r => r.json())
      .then(data => {
        if (data.error) { showError(data.error); return; }
        allRows = data.results || [];
        updateKPIs(data);
        syncSidebarDte(data);
        applyFilters();   // also refreshes the chart from filteredRows
        const ts = data.scan_time || "";
        if (ts) {
          $("last-scan-time").textContent = "Last scan: " + ts;
          $("kpi-scan-time").textContent  = "Scanned " + ts;
        }
        const count = allRows.length;
        showSuccess(`✓ Scan complete — ${count} opportunit${count === 1 ? "y" : "ies"} found`);
        loadScanHistory();
      })
      .catch(err => showError("Could not load results: " + err.message));
  }

  function loadScanHistory() {
    fetch("/api/scans")
      .then(r => r.json())
      .then(scans => {
        const sel = $("scan-history");
        sel.innerHTML = scans.map(s =>
          `<option value="${s.timestamp}">${s.scan_time || s.timestamp}</option>`
        ).join("");
      })
      // H5: show error state instead of leaving "Loading…" forever
      .catch(() => {
        $("scan-history").innerHTML = `<option value="">Error loading history</option>`;
      });
  }

  function loadScanByTimestamp(ts) {
    fetch(`/api/results/${ts}`)
      .then(r => r.json())
      .then(data => {
        if (data.error) { showError(data.error); return; }
        allRows = data.results || [];
        updateKPIs(data);
        syncSidebarDte(data);
        applyFilters();   // also refreshes the chart from filteredRows
      })
      .catch(err => showError("Could not load scan: " + err.message));
  }

  // ── KPIs ──────────────────────────────────────────────────────────────────
  function updateKPIs(data) {
    const rows    = data.results || [];
    const symbols = new Set(rows.map(r => r.symbol)).size;
    const { min, max } = getDteRange();
    $("kpi-total").textContent   = rows.length;
    // C5: KPI flagged count from filteredRows so it matches the tab count
    const flagged = filteredRows.length
      ? filteredRows.filter(r => r.flagged).length
      : rows.filter(r => r.flagged).length;
    $("kpi-flagged").textContent = flagged;
    $("kpi-symbols").textContent = symbols;
    $("kpi-dte").textContent     = `${min}–${max}d`;
  }

  // ── Filters + render ──────────────────────────────────────────────────────
  function applyFilters() {
    const ticker     = ($("filter-ticker").value || "").toUpperCase().trim();
    const minYield   = parseFloat($("filter-min-yield").value)  || 0;
    const maxDelta   = parseFloat($("filter-max-delta").value)  || 0.35;
    const dteMin     = parseInt($("filter-dte-min").value)      || 0;
    const dteMax     = parseInt($("filter-dte-max").value)      || 9999;
    const flagOnly   = $("filter-flagged-only").checked;
    const account    = getAccountSize();

    filteredRows = allRows.filter(r => {
      if (ticker && !r.symbol.toUpperCase().includes(ticker)) return false;
      if ((r.realistic_yield || 0) < minYield) return false;
      if (Math.abs(r.delta || 0) > maxDelta) return false;
      if ((r.days_to_expiration || 0) < dteMin) return false;
      if ((r.days_to_expiration || 0) > dteMax) return false;
      if (flagOnly && !r.flagged) return false;
      if (account > 0 && (r.capital_required || 0) > account) return false;
      return true;
    });

    filteredRows = sortRows(filteredRows, sortCol, sortDir);
    const tabRows = tabFilter(filteredRows, currentTab);

    // C5: update flagged KPI from filtered set
    $("kpi-flagged").textContent = filteredRows.filter(r => r.flagged).length;

    // Banded picks ignore the ticker filter — show best trade from the whole scan
    const bandRows = allRows.filter(r => {
      if ((r.realistic_yield || 0) < minYield) return false;
      if (Math.abs(r.delta || 0) > maxDelta) return false;
      if ((r.days_to_expiration || 0) < dteMin) return false;
      if ((r.days_to_expiration || 0) > dteMax) return false;
      if (flagOnly && !r.flagged) return false;
      if (account > 0 && (r.capital_required || 0) > account) return false;
      return true;
      // NOTE: ticker filter intentionally excluded
    });

    $("row-count").textContent = `${tabRows.length} result${tabRows.length === 1 ? "" : "s"}`;
    renderTable(tabRows);
    renderBandedPicks(bandRows);
    updateChart();

    // Update filter summary
    const active = [];
    if (ticker) active.push(`Ticker: ${ticker}`);
    if (minYield > 0) active.push(`Yield ≥${minYield}%`);
    if (maxDelta < 0.35) active.push(`Δ ≤${maxDelta}`);
    if (flagOnly) active.push("High Yield only");
    $("filter-summary").textContent = active.length ? active.join(" · ") : "";
  }

  function tabFilter(rows, tab) {
    // H6: clear sort indicators when tab overrides sort
    if (tab !== "all") {
      document.querySelectorAll("#results-table th").forEach(h =>
        h.classList.remove("sort-asc", "sort-desc")
      );
    }
    switch (tab) {
      case "flagged":
        return sortRows(rows.filter(r => r.flagged), "realistic_yield", "desc");
      case "safest":
        // H3: single-pass sort — OI desc primary, abs(delta) asc secondary
        return [...rows].sort((a, b) => {
          if (b.open_interest !== a.open_interest)
            return (b.open_interest || 0) - (a.open_interest || 0);
          return Math.abs(a.delta || 0) - Math.abs(b.delta || 0);
        });
      case "highest_yield":
        // M5: sort by realistic_yield (the displayed column) not risk_adjusted_yield
        return sortRows(rows, "realistic_yield", "desc");
      case "balanced": {
        // Ranked by Income Efficiency ($/day per $1k capital at risk).
        // DTE-neutral, capital-normalized, liquidity is a gate not a score.
        return [...rows]
          .filter(r => (r.open_interest || 0) >= 500)
          .map(r => ({ ...r, _eff: incomeEfficiency(r) }))
          .sort((a, b) => b._eff - a._eff);
      }
      default:
        return rows;
    }
  }

  // ── Income Efficiency (new metric) ─────────────────────────────────────────
  // Premium income per day per $1,000 of capital at risk.
  // DTE-neutral (no annualization), capital-normalized. Liquidity is a gate.
  function incomeEfficiency(r) {
    const cap  = r.capital_required || (r.strike * 100) || 0;
    const days = r.days_to_expiration || 0;
    if (cap <= 0 || days <= 0) return 0;
    const premiumIncome = (r.premium || 0) * 100;        // $ per contract
    return (premiumIncome / cap / days) * 1000;          // $/day per $1k capital
  }

  // Delta bands for risk appetite
  const DELTA_BANDS = {
    conservative: { min: 0,    max: 0.15 },
    standard:     { min: 0.15, max: 0.22 },
    aggressive:   { min: 0.22, max: 0.30 },
  };

  // Best contract per band, by income efficiency, one per symbol, OI gate >=500.
  function bandPick(rows, band) {
    const b = DELTA_BANDS[band];
    const eligible = rows.filter(r => {
      const d = Math.abs(r.delta || 0);
      return d > b.min && d <= b.max && (r.open_interest || 0) >= 500;
    });
    if (!eligible.length) return null;
    // dedupe by symbol keeping best efficiency, then pick the top
    const best = new Map();
    for (const r of eligible) {
      const eff = incomeEfficiency(r);
      const cur = best.get(r.symbol);
      if (!cur || eff > cur._eff) best.set(r.symbol, { ...r, _eff: eff });
    }
    return Array.from(best.values()).sort((a, b) => b._eff - a._eff)[0] || null;
  }

  function sortRows(rows, col, dir) {
    return [...rows].sort((a, b) => {
      let av = a[col], bv = b[col];
      if (col === "symbol" || col === "expiration") {
        av = String(av || ""); bv = String(bv || "");
        return dir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
      }
      av = parseFloat(av) || 0; bv = parseFloat(bv) || 0;
      return dir === "asc" ? av - bv : bv - av;
    });
  }

  // ── Banded Picks (Conservative / Standard / Aggressive) ────────────────────
  function renderBandedPicks(rows) {
    const wrap = $("banded-picks");
    if (!rows.length) { wrap.classList.add("hidden"); return; }

    let any = false;
    for (const band of ["conservative", "standard", "aggressive"]) {
      const el = document.querySelector(`#band-${band} .band-body`);
      const r = bandPick(rows, band);
      if (!r) {
        el.innerHTML = `<div class="band-empty">No qualifying contract in this risk band.</div>`;
        continue;
      }
      any = true;
      el.innerHTML = `
        <div class="band-symbol">${r.symbol}</div>
        <div class="band-row"><span>Strike</span><strong>$${fmt2(r.strike)}</strong></div>
        <div class="band-row"><span>Expiry</span><strong>${r.expiration || "—"} (${r.days_to_expiration || "—"}d)</strong></div>
        <div class="band-row"><span>Premium</span><strong>$${fmt2(r.premium)}</strong></div>
        <div class="band-row"><span>Delta</span><strong>${fmt2(r.delta)}</strong></div>
        <div class="band-row"><span>Capital</span><strong>$${Math.round(r.capital_required || 0).toLocaleString()}</strong></div>
        <div class="band-row band-eff"><span>Income eff.</span><strong>$${fmt2(r._eff)}<small>/day per $1k</small></strong></div>
        <div class="band-row band-yield"><span>Real Yield</span><strong>${fmt2(r.realistic_yield)}%</strong></div>
        <div class="band-row band-tech"><span>Tech Score</span><strong class="tech-score tech-score--${techBand(r.tech_score)}">${r.tech_score != null ? r.tech_score + "/100" : "—"}</strong></div>
        ${r.pivot_1d_s1 != null ? `<div class="band-row"><span>Daily</span><strong>S: $${fmt2(r.pivot_1d_s1)} | P: $${fmt2(r.pivot_1d_pp)} | R: $${fmt2(r.pivot_1d_r1)}</strong></div>` : ""}
        ${r.pivot_1w_s1 != null ? `<div class="band-row"><span>Weekly</span><strong>S: $${fmt2(r.pivot_1w_s1)} | P: $${fmt2(r.pivot_1w_pp)} | R: $${fmt2(r.pivot_1w_r1)}</strong></div>` : ""}
        ${r.pivot_1m_s1 != null ? `<div class="band-row"><span>Monthly</span><strong>S: $${fmt2(r.pivot_1m_s1)} | P: $${fmt2(r.pivot_1m_pp)}</strong></div>` : ""}
        ${r.bb_pct_b != null ? `<div class="band-row"><span>BB %B</span><strong>${fmt1(r.bb_pct_b * 100)}%</strong></div>` : ""}
      `;
    }
    wrap.classList.toggle("hidden", !any);
  }

  // ── Table render ──────────────────────────────────────────────────────────
  function renderTable(rows) {
    if (currentTab === "positions" || currentTab === "orders") return;
    const tbody = $("results-body");
    // C3: always use full colspan (15+1 for trade col when connected)
    const COLSPAN = 15;

    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="${COLSPAN}" class="empty-cell">No results match the current filters.</td></tr>`;
      return;
    }

    const account = getAccountSize();
    tbody.innerHTML = rows.map(r => {
      const cls = rowClass(r);
      // C4: amber when capital exceeds full account (not 20%)
      const capHigh = (account > 0 && (r.capital_required || 0) > account) ? "col-capital-high" : "";
      // M2: use != null check so 0 days shows "⚠ 0d"
      const earnWarn = r.earnings_in_window
        ? `<span class="earnings-warn" title="Earnings in ${r.days_to_earnings != null ? r.days_to_earnings : "?"} days">⚠${r.days_to_earnings != null ? " " + r.days_to_earnings + "d" : ""}</span>`
        : "";
      const flag = r.flagged ? `<span class="badge-flagged" title="High yield + deep OTM — verify IV">⚡</span>` : "";

      return `<tr class="${cls}">
        <td><strong>${r.symbol}</strong>${earnWarn}</td>
        <td>$${fmt2(r.current_price)}</td>
        <td>$${fmt2(r.strike)}</td>
        <td>${r.expiration || "—"}<br><small style="color:var(--text-3)">${r.days_to_expiration || "—"}d</small></td>
        <td>$${fmt2(r.premium)}</td>
        <td>${fmt2(r.delta)}</td>
        <td><strong>${fmt2(r.realistic_yield)}%</strong></td>
        <td class="${capHigh}">$${Math.round(r.capital_required || 0).toLocaleString()}</td>
        <td>${flag}</td>
        <td class="col-extra${colsExpanded ? " show" : ""}">${fmt1(r.implied_volatility)}%</td>
        <td class="col-extra${colsExpanded ? " show" : ""}">$${fmt2(Math.abs(r.theta_per_contract || 0))}</td>
        <td class="col-extra${colsExpanded ? " show" : ""}">${(r.open_interest || 0).toLocaleString()}</td>
        <td class="col-extra${colsExpanded ? " show" : ""}">${fmt1(r.distance_otm)}%</td>
        <td class="col-extra${colsExpanded ? " show" : ""}">${fmt2(r.risk_adjusted_yield)}%</td>
        <td class="col-extra${colsExpanded ? " show" : ""}">${fmt2(r.bid_ask_spread_pct)}%</td>
        <td class="col-extra${colsExpanded ? " show" : ""}">
          ${r.tech_score != null
            ? `<span class="tech-score tech-score--${techBand(r.tech_score)}">${r.tech_score}</span>`
            : "—"}
        </td>
        <td class="col-extra${colsExpanded ? " show" : ""}">${fmtPivot(r.pivot_1d_s1)}</td>
        <td class="col-extra${colsExpanded ? " show" : ""}">${fmtPivot(r.pivot_1d_pp)}</td>
        <td class="col-extra${colsExpanded ? " show" : ""}">${fmtPivot(r.pivot_1d_r1)}</td>
        <td class="col-extra${colsExpanded ? " show" : ""}">${fmtPivot(r.pivot_1w_s1)}</td>
        <td class="col-extra${colsExpanded ? " show" : ""}">${fmtPivot(r.pivot_1w_pp)}</td>
        <td class="col-extra${colsExpanded ? " show" : ""}">${fmtPivot(r.pivot_1w_r1)}</td>
        <td class="col-extra${colsExpanded ? " show" : ""}">${fmtPivot(r.pivot_1w_s2)}</td>
        <td class="col-extra${colsExpanded ? " show" : ""}">${fmtPivot(r.pivot_1m_s1)}</td>
        <td class="col-extra${colsExpanded ? " show" : ""}">${fmtPivot(r.pivot_1m_pp)}</td>
        <td class="col-extra${colsExpanded ? " show" : ""}">${fmtPivot(r.bb_upper)}</td>
        <td class="col-extra${colsExpanded ? " show" : ""}">${fmtPivot(r.bb_middle)}</td>
        <td class="col-extra${colsExpanded ? " show" : ""}">${fmtPivot(r.bb_lower)}</td>
        <td class="col-extra${colsExpanded ? " show" : ""}">
          ${r.bb_pct_b != null ? fmt1(r.bb_pct_b * 100) + "%" : "—"}
        </td>
        <td class="col-extra${colsExpanded ? " show" : ""}">
          ${r.bb_width_pct != null ? fmt1(r.bb_width_pct) + "%" : "—"}
        </td>
      </tr>`;
    }).join("");
    // Inject Sell Put buttons if Alpaca is connected
    injectSellPutButtons(rows);
  }

  function rowClass(r) {
    if (r.earnings_in_window) return "row-earnings";
    if (r.flagged)            return "row-flagged";
    if ((r.realistic_yield || 0) >= 15) return "row-good";
    if (Math.abs(r.delta || 0) > 0.25)  return "row-risky";
    return "";
  }

  // ── Chart ─────────────────────────────────────────────────────────────────
  let chartInstance = null;

  // Keep only the best contract per symbol, by the given numeric key.
  function dedupeBySymbol(rows, key = "_score") {
    const best = new Map();
    for (const r of rows) {
      const existing = best.get(r.symbol);
      if (!existing || (r[key] || 0) > (existing[key] || 0)) best.set(r.symbol, r);
    }
    return Array.from(best.values());
  }

  function updateChart() {
    const canvas = document.getElementById("yield-chart");
    if (!canvas) return;

    const account = getAccountSize();

    // The Top 10 chart is a market overview — it reflects the whole scan,
    // NOT the sidebar filters. Only OI >= 500 and account affordability apply.
    // H2: destroy stale chart if no eligible rows
    const eligible = allRows.filter(r =>
      (r.open_interest || 0) >= 500 &&
      (account === 0 || (r.capital_required || 0) <= account)
    );

    if (!eligible.length) {
      if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
      return;
    }

    // Ranked by Income Efficiency ($/day per $1k capital), one contract per symbol.
    const scored = eligible.map(r => ({ ...r, _eff: incomeEfficiency(r) }));
    const deduped = dedupeBySymbol(scored, "_eff");
    deduped.sort((a, b) => b._eff - a._eff);
    const top = deduped.slice(0, 10);

    const labels = top.map(r => r.symbol);
    const values = top.map(r => parseFloat((r._eff || 0).toFixed(2)));
    const colors = top.map(r => {
      const d = Math.abs(r.delta || 0);
      if (d <= 0.15) return "#22c55e";
      if (d <= 0.22) return "#3b82f6";
      return "#f59e0b";
    });

    if (chartInstance) chartInstance.destroy();
    chartInstance = new Chart(canvas, {
      type: "bar",
      data: {
        labels,
        datasets: [{
          data: values,
          backgroundColor: colors,
          borderRadius: 4,
          borderSkipped: false,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: ctx => {
                const r = top[ctx[0].dataIndex];
                return `${r.symbol} — #${ctx[0].dataIndex + 1}`;
              },
              label: ctx => {
                const r = top[ctx.dataIndex];
                return [
                  `Income eff: $${fmt2(r._eff)}/day per $1k`,
                  `Real Yield: ${fmt2(r.realistic_yield)}%`,
                  `Delta:      ${fmt2(r.delta)}`,
                  `Strike:     $${fmt2(r.strike)} (${r.days_to_expiration || "—"}d)`,
                  `OI:         ${(r.open_interest || 0).toLocaleString()}`,
                  `Capital:    $${Math.round(r.capital_required || 0).toLocaleString()}`,
                ];
              },
            },
          },
        },
        scales: {
          x: {
            ticks: { color: "#94a3b8", font: { size: 11 } },
            grid:  { color: "rgba(255,255,255,.05)" },
          },
          y: {
            ticks: { color: "#94a3b8", font: { size: 11 },
                     callback: v => "$" + v },
            title: { display: true, text: "$/day per $1k capital",
                     color: "#64748b", font: { size: 10 } },
            grid:  { color: "rgba(255,255,255,.05)" },
          },
        },
      },
    });
  }

  // ── Floating tooltips (Salesforce-style) ──────────────────────────────────
  function initTooltips() {
    const tip = $("col-tooltip");
    document.addEventListener("mouseover", e => {
      const el = e.target.closest(".col-info");
      if (!el) return;
      const text = el.dataset.tip;
      if (!text) return;
      tip.textContent = text;
      tip.style.opacity = "1";
    });
    document.addEventListener("mousemove", e => {
      if (tip.style.opacity !== "1") return;
      let x = e.clientX + 14, y = e.clientY + 14;
      const tw = tip.offsetWidth, th = tip.offsetHeight;
      // M1: clamp all four edges
      if (x + tw > window.innerWidth  - 8) x = e.clientX - tw - 14;
      if (y + th > window.innerHeight - 8) y = e.clientY - th - 14;
      if (x < 8) x = e.clientX + 14;
      if (y < 8) y = e.clientY + 14;
      tip.style.left = x + "px";
      tip.style.top  = y + "px";
    });
    document.addEventListener("mouseout", e => {
      if (!e.target.closest(".col-info")) return;
      tip.style.opacity = "0";
    });
  }

  // ── Sort on header click ──────────────────────────────────────────────────
  function initTableSort() {
    document.querySelector("#results-table thead").addEventListener("click", e => {
      const th = e.target.closest("th[data-sort]");
      if (!th) return;
      const col = th.dataset.sort;
      if (sortCol === col) sortDir = sortDir === "asc" ? "desc" : "asc";
      else { sortCol = col; sortDir = "desc"; }
      document.querySelectorAll("#results-table th").forEach(h => {
        h.classList.remove("sort-asc", "sort-desc");
      });
      th.classList.add(sortDir === "asc" ? "sort-asc" : "sort-desc");
      applyFilters();
    });
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  function fmt2(v) { return (parseFloat(v) || 0).toFixed(2); }
  function fmt1(v) { return (parseFloat(v) || 0).toFixed(1); }

  // Tech Score colour band
  function techBand(score) {
    if (score == null) return "na";
    if (score >= 70)   return "strong";
    if (score >= 50)   return "marginal";
    return "weak";
  }

  // Render a pivot price cell: "$123.45" or "—"
  function fmtPivot(v) { return v != null ? "$" + fmt2(v) : "—"; }

  function showSuccess(msg) {
    const el = $("success-banner");
    el.textContent = msg;
    el.classList.remove("hidden");
    setTimeout(() => el.classList.add("hidden"), 4000);
  }

  function showError(msg) {
    const el = $("error-banner");
    el.textContent = msg;
    el.classList.remove("hidden");
  }

  // ── Alpaca integration ────────────────────────────────────────────────────

  // ---- Credential helpers ----
  function alpacaKey()    { return localStorage.getItem("alpaca_key")    || ""; }
  function alpacaSecret() { return localStorage.getItem("alpaca_secret") || ""; }
  function isAlpacaConnected() { return !!(alpacaKey() && alpacaSecret()); }
  function alpacaHeaders() {
    return {
      "X-APCA-Key":    alpacaKey(),
      "X-APCA-Secret": alpacaSecret(),
    };
  }

  // ---- Account panel ----
  function renderAlpacaPanel(acct) {
    const panel = $("alpaca-panel");
    const body  = $("alpaca-panel-body");
    panel.classList.remove("hidden");
    body.innerHTML = `
      <div class="alpaca-kpi"><span class="alpaca-kpi-label">Cash</span><span class="alpaca-kpi-value">$${(acct.cash||0).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}</span></div>
      <div class="alpaca-kpi"><span class="alpaca-kpi-label">Buying Power</span><span class="alpaca-kpi-value">$${(acct.buying_power||0).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}</span></div>
      <div class="alpaca-kpi"><span class="alpaca-kpi-label">Portfolio</span><span class="alpaca-kpi-value">$${(acct.portfolio_value||0).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}</span></div>
      <div class="alpaca-kpi alpaca-kpi--status"><span class="alpaca-kpi-label">Status</span><span class="alpaca-kpi-value alpaca-status-dot">${acct.status || "—"}</span></div>
    `;
  }

  function renderAlpacaPlaceholder() {
    const body = $("alpaca-panel-body");
    body.innerHTML = `
      <div class="account-placeholder">
        <span>Connect your Alpaca paper account</span>
        <button class="link-btn" id="alpaca-connect-link">Set up credentials →</button>
      </div>
    `;
    document.getElementById("alpaca-connect-link")?.addEventListener("click", openAlpacaSettings);
  }

  async function loadAlpacaAccount() {
    if (!isAlpacaConnected()) {
      $("alpaca-panel").classList.remove("hidden");
      renderAlpacaPlaceholder();
      return;
    }
    try {
      const r = await fetch("/api/alpaca/account", { headers: alpacaHeaders() });
      const d = await r.json();
      if (d.error) { showError("Alpaca: " + d.error); return; }
      renderAlpacaPanel(d);
    } catch(e) {
      showError("Could not reach Alpaca: " + e.message);
    }
  }

  // ---- Positions + Orders tabs ----
  async function loadAndRenderPositions() {
    const tbody = $("results-body");
    tbody.innerHTML = `<tr><td colspan="16" class="empty-cell">Loading positions…</td></tr>`;
    try {
      const r = await fetch("/api/alpaca/positions", { headers: alpacaHeaders() });
      const positions = await r.json();
      if (positions.error) throw new Error(positions.error);
      if (!positions.length) {
        tbody.innerHTML = `<tr><td colspan="16" class="empty-cell">No open positions in your paper account.</td></tr>`;
        return;
      }
      // Swap table header for positions view
      document.querySelector("#results-table thead tr").innerHTML = `
        <th>Symbol</th><th>Qty</th><th>Side</th><th>Avg Cost</th>
        <th>Current Price</th><th>Market Value</th>
        <th>Unrealized P&L</th><th>P&L %</th><th>Asset Class</th>
      `;
      tbody.innerHTML = positions.map(p => {
        const pl = p.unrealized_pl || 0;
        const plPct = (p.unrealized_plpc || 0) * 100;
        const plCls = pl >= 0 ? "pl-pos" : "pl-neg";
        return `<tr>
          <td><strong>${p.symbol}</strong></td>
          <td>${p.qty}</td>
          <td>${p.side}</td>
          <td>$${fmt2(p.avg_entry_price)}</td>
          <td>$${fmt2(p.current_price)}</td>
          <td>$${fmt2(p.market_value)}</td>
          <td class="${plCls}">${pl >= 0 ? "+" : ""}$${fmt2(pl)}</td>
          <td class="${plCls}">${pl >= 0 ? "+" : ""}${fmt2(plPct)}%</td>
          <td>${p.asset_class}</td>
        </tr>`;
      }).join("");
    } catch(e) {
      tbody.innerHTML = `<tr><td colspan="16" class="empty-cell">Error loading positions: ${e.message}</td></tr>`;
    }
  }

  async function loadAndRenderOrders() {
    const tbody = $("results-body");
    tbody.innerHTML = `<tr><td colspan="16" class="empty-cell">Loading orders…</td></tr>`;
    try {
      const r = await fetch("/api/alpaca/orders?limit=20", { headers: alpacaHeaders() });
      const orders = await r.json();
      if (orders.error) throw new Error(orders.error);
      if (!orders.length) {
        tbody.innerHTML = `<tr><td colspan="16" class="empty-cell">No recent orders found.</td></tr>`;
        return;
      }
      document.querySelector("#results-table thead tr").innerHTML = `
        <th>Symbol</th><th>Side</th><th>Qty</th><th>Type</th>
        <th>Status</th><th>Limit Price</th><th>Fill Price</th><th>Filled At</th>
      `;
      tbody.innerHTML = orders.map(o => `<tr>
        <td><strong>${o.symbol}</strong></td>
        <td>${o.side}</td>
        <td>${o.qty || "—"}</td>
        <td>${o.type}</td>
        <td><span class="order-status order-status--${(o.status||"").toLowerCase()}">${o.status}</span></td>
        <td>${o.limit_price != null ? "$" + fmt2(o.limit_price) : "—"}</td>
        <td>${o.filled_avg_price != null ? "$" + fmt2(o.filled_avg_price) : "—"}</td>
        <td>${o.filled_at ? o.filled_at.replace("T"," ").slice(0,19) : "—"}</td>
      </tr>`).join("");
    } catch(e) {
      tbody.innerHTML = `<tr><td colspan="16" class="empty-cell">Error loading orders: ${e.message}</td></tr>`;
    }
  }

  // Restore the scanner table header (called when switching away from alpaca tabs)
  function restoreScannerTableHeader() {
    document.querySelector("#results-table thead tr").innerHTML = `
      <th data-sort="symbol">Symbol</th>
      <th data-sort="current_price">Price</th>
      <th data-sort="strike">Strike</th>
      <th data-sort="expiration">Expiry (DTE)</th>
      <th data-sort="premium">Premium</th>
      <th data-sort="delta">Delta</th>
      <th data-sort="realistic_yield" class="col-yield">Real Yield %</th>
      <th data-sort="capital_required">Capital</th>
      <th data-sort="flagged">Flag</th>
      <th data-sort="implied_volatility" class="col-extra${colsExpanded ? " show" : ""}">IV %</th>
      <th data-sort="theta_per_contract" class="col-extra${colsExpanded ? " show" : ""}">θ/day</th>
      <th data-sort="open_interest" class="col-extra${colsExpanded ? " show" : ""}">OI</th>
      <th data-sort="distance_otm" class="col-extra${colsExpanded ? " show" : ""}">OTM %</th>
      <th data-sort="risk_adjusted_yield" class="col-extra${colsExpanded ? " show" : ""}">Risk-Adj %</th>
      <th data-sort="bid_ask_spread_pct" class="col-extra${colsExpanded ? " show" : ""}">Spread %</th>
      <th data-sort="tech_score" class="col-extra${colsExpanded ? " show" : ""}">Tech Score</th>
      <th data-sort="pivot_1d_s1" class="col-extra${colsExpanded ? " show" : ""}">D.S1</th>
      <th data-sort="pivot_1d_pp" class="col-extra${colsExpanded ? " show" : ""}">D.PP</th>
      <th data-sort="pivot_1d_r1" class="col-extra${colsExpanded ? " show" : ""}">D.R1</th>
      <th data-sort="pivot_1w_s1" class="col-extra${colsExpanded ? " show" : ""}">W.S1</th>
      <th data-sort="pivot_1w_pp" class="col-extra${colsExpanded ? " show" : ""}">W.PP</th>
      <th data-sort="pivot_1w_r1" class="col-extra${colsExpanded ? " show" : ""}">W.R1</th>
      <th data-sort="pivot_1w_s2" class="col-extra${colsExpanded ? " show" : ""}">W.S2</th>
      <th data-sort="pivot_1m_s1" class="col-extra${colsExpanded ? " show" : ""}">M.S1</th>
      <th data-sort="pivot_1m_pp" class="col-extra${colsExpanded ? " show" : ""}">M.PP</th>
      <th data-sort="bb_upper" class="col-extra${colsExpanded ? " show" : ""}">BB Upper</th>
      <th data-sort="bb_middle" class="col-extra${colsExpanded ? " show" : ""}">BB Mid</th>
      <th data-sort="bb_lower" class="col-extra${colsExpanded ? " show" : ""}">BB Lower</th>
      <th data-sort="bb_pct_b" class="col-extra${colsExpanded ? " show" : ""}">BB %B</th>
      <th data-sort="bb_width_pct" class="col-extra${colsExpanded ? " show" : ""}">BB Width</th>
      <th class="col-trade alpaca-col${isAlpacaConnected() ? "" : " hidden"}" id="th-trade">Trade</th>
    `;
    // Re-bind sort listener
    initTableSort();
  }

  // ---- Sell Put button injection (called after scanner renderTable) ----
  function injectSellPutButtons(rows) {
    if (!isAlpacaConnected()) return;
    const trs = document.querySelectorAll("#results-body tr");
    trs.forEach((tr, i) => {
      if (!rows[i]) return;
      const r = rows[i];
      const td = document.createElement("td");
      td.className = "col-trade";
      const btn = document.createElement("button");
      btn.className = "btn-sell-put";
      btn.textContent = "Sell Put";
      btn.addEventListener("click", (e) => { e.stopPropagation(); openTradeModal(r); });
      td.appendChild(btn);
      tr.appendChild(td);
    });
  }

  // ---- Trade Review Modal ----
  let _pendingTradeRow = null;

  function openTradeModal(r) {
    _pendingTradeRow = r;
    const midPrice = r.premium || 0;  // premium is already mid = (bid+ask)/2
    $("trade-review-headline").textContent =
      `SELL 1 × ${r.symbol} $${fmt2(r.strike)}P  ${r.expiration || "—"}`;
    $("trade-review-price").textContent =
      `$${fmt2(midPrice)}/share ($${fmt2(midPrice * 100)} total)`;
    $("trade-review-capital").textContent =
      `$${Math.round(r.capital_required || 0).toLocaleString()}`;
    $("trade-review-yield").textContent = `${fmt2(r.realistic_yield)}%`;
    $("trade-review-delta").textContent  = fmt2(r.delta);
    $("trade-review-dte").textContent    = `${r.days_to_expiration || "—"} days`;
    $("trade-modal-overlay").classList.remove("hidden");
  }

  async function submitOrder() {
    if (!_pendingTradeRow) return;
    const r = _pendingTradeRow;
    const btn = $("trade-confirm-btn");
    btn.disabled = true;
    btn.textContent = "Submitting…";
    try {
      const resp = await fetch("/api/alpaca/order", {
        method: "POST",
        headers: { ...alpacaHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol:      r.symbol,
          expiration:  r.expiration,
          strike:      r.strike,
          limit_price: r.premium,
          qty:         1,
        }),
      });
      const d = await resp.json();
      if (d.error) throw new Error(d.error);
      $("trade-modal-overlay").classList.add("hidden");
      showSuccess(`✓ Order submitted: ${r.symbol} $${fmt2(r.strike)}P ${r.expiration} — ID: ${d.id}`);
      // Refresh account + positions
      loadAlpacaAccount();
    } catch(e) {
      showError("Order failed: " + e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "✓ Submit to Alpaca";
      _pendingTradeRow = null;
    }
  }

  // ---- Settings modal ----
  // ── Provider status ────────────────────────────────────────────────────────
  async function loadProviderStatus() {
    try {
      const res = await fetch("/api/providers");
      const d = await res.json();
      const setDot = (id, on, label) => {
        const el = document.getElementById(id);
        if (!el) return;
        const dot = el.querySelector(".provider-dot");
        if (dot) {
          dot.className = "provider-dot " + (on ? "provider-dot--on" : "provider-dot--off");
          dot.title = on ? `${label}: active` : `${label}: not configured`;
        }
      };
      setDot("badge-tradier",     d.tradier,      "Tradier");
      setDot("badge-alpaca-data", d.alpaca_data,  "Alpaca Data");
    } catch(_) {}
  }

  function openAlpacaSettings() {
    $("alpaca-key-input").value    = alpacaKey();
    $("alpaca-secret-input").value = alpacaSecret();
    loadProviderStatus();
    $("alpaca-modal-overlay").classList.remove("hidden");
  }

  async function saveAlpacaCredentials() {
    const key    = $("alpaca-key-input").value.trim();
    const secret = $("alpaca-secret-input").value.trim();
    if (!key || !secret) { showError("Both API Key and Secret are required."); return; }

    // 1. Save Alpaca trading creds to localStorage (for trade execution)
    localStorage.setItem("alpaca_key",    key);
    localStorage.setItem("alpaca_secret", secret);

    // 2. Also save to server credentials.json (for scanner background process)
    try {
      const resp = await fetch("/api/providers/credentials", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ alpaca_key: key, alpaca_secret: secret }),
      });
      const result = await resp.json();
      // Update Alpaca data provider dot
      const el = document.getElementById("badge-alpaca-data");
      if (el) {
        const dot = el.querySelector(".provider-dot");
        if (dot) dot.className = "provider-dot " + (result.alpaca_data ? "provider-dot--on" : "provider-dot--off");
      }
    } catch(_) {}

    $("alpaca-modal-overlay").classList.add("hidden");
    document.querySelectorAll(".tab-alpaca").forEach(t => t.classList.remove("hidden"));
    document.querySelectorAll(".alpaca-col").forEach(el => el.classList.remove("hidden"));
    loadAlpacaAccount();
    showSuccess("✓ Alpaca connected. Scanner will use Alpaca data on next scan.");
  }

  function clearAlpacaCredentials() {
    localStorage.removeItem("alpaca_key");
    localStorage.removeItem("alpaca_secret");
    $("alpaca-modal-overlay").classList.add("hidden");
    document.querySelectorAll(".tab-alpaca").forEach(t => t.classList.add("hidden"));
    document.querySelectorAll(".alpaca-col").forEach(el => el.classList.add("hidden"));
    renderAlpacaPlaceholder();
    showSuccess("Alpaca credentials cleared.");
  }

  // ── Init ──────────────────────────────────────────────────────────────────
  function init() {
    loadAccountSize();
    setPreset("STANDARD");
    loadProviderStatus();
    initTooltips();
    initTableSort();

    // DTE preset buttons
    document.querySelectorAll(".btn-dte").forEach(btn => {
      btn.addEventListener("click", () => {
        setPreset(btn.dataset.preset);
        if (btn.dataset.preset === "CUSTOM") {
          const { min, max } = getDteRange();
          $("dte-badge").textContent = `${min}–${max} DTE`;
        }
      });
    });

    // Custom DTE inputs update badge
    [$("dte-min-input"), $("dte-max-input")].forEach(inp => {
      inp.addEventListener("input", () => {
        const min = $("dte-min-input").value || "?";
        const max = $("dte-max-input").value || "?";
        $("dte-badge").textContent = `${min}–${max} DTE`;
      });
    });

    // Account size save + re-filter
    $("account-size-input").addEventListener("change", () => {
      saveAccountSize();
      applyFilters();
    });

    // Run scan
    $("run-scan-btn").addEventListener("click", startScan);

    // History buttons
    $("history-btn").addEventListener("click", () => {
      const sel = $("scan-history");
      sel.classList.toggle("hidden");
      if (!sel.classList.contains("hidden")) loadScanHistory();
    });
    $("scan-history").addEventListener("change", e => {
      if (e.target.value) loadScanByTimestamp(e.target.value);
    });

    // Guide drawer
    const drawer  = $("guide-drawer");
    const overlay = $("guide-overlay");
    function openGuide()  { drawer.classList.add("open"); overlay.classList.remove("hidden"); drawer.removeAttribute("aria-hidden"); }
    function closeGuide() { drawer.classList.remove("open"); overlay.classList.add("hidden"); drawer.setAttribute("aria-hidden", "true"); }
    $("guide-btn").addEventListener("click", openGuide);
    $("guide-text-btn").addEventListener("click", openGuide);
    $("guide-close").addEventListener("click", closeGuide);
    overlay.addEventListener("click", closeGuide);

    // Tabs — H6: clear sort indicators when switching tabs
    document.querySelectorAll(".tab").forEach(tab => {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
        tab.classList.add("active");
        const prevTab = currentTab;
        currentTab = tab.dataset.tab;

        // Alpaca-specific tabs: custom render, don't run scanner applyFilters
        if (currentTab === "positions") {
          if (!isAlpacaConnected()) { showError("Connect Alpaca first (⚙️ button)."); return; }
          restoreScannerTableHeader();
          loadAndRenderPositions();
          $("row-count").textContent = "";
          $("banded-picks").classList.add("hidden");
          return;
        }
        if (currentTab === "orders") {
          if (!isAlpacaConnected()) { showError("Connect Alpaca first (⚙️ button)."); return; }
          restoreScannerTableHeader();
          loadAndRenderOrders();
          $("row-count").textContent = "";
          $("banded-picks").classList.add("hidden");
          return;
        }

        // Switching back from Alpaca tabs — restore scanner header first
        if (prevTab === "positions" || prevTab === "orders") {
          restoreScannerTableHeader();
        }

        // Clear column sort indicators since tab has its own ordering
        if (currentTab !== "all") {
          document.querySelectorAll("#results-table th").forEach(h =>
            h.classList.remove("sort-asc", "sort-desc")
          );
        }
        applyFilters();
      });
    });

    // Column toggle — M3: reset sort to default when collapsing extra cols
    $("cols-toggle").addEventListener("click", () => {
      const wasExpanded = colsExpanded;
      colsExpanded = !colsExpanded;
      $("cols-toggle").classList.toggle("active", colsExpanded);
      $("cols-toggle").textContent = colsExpanded ? "⊖ Less columns" : "⊕ More columns";
      // L1: update aria-pressed
      $("cols-toggle").setAttribute("aria-pressed", String(colsExpanded));
      document.querySelectorAll(".col-extra").forEach(el => {
        el.classList.toggle("show", colsExpanded);
      });
      // M3: if collapsing and sort was on a hidden col, reset to default
      if (wasExpanded && !colsExpanded) {
        const extraCols = [
          "implied_volatility","theta_per_contract","open_interest","distance_otm",
          "risk_adjusted_yield","bid_ask_spread_pct",
          "tech_score","pivot_1w_pp","pivot_1w_s1","pivot_1w_s2",
          "pivot_1m_pp","pivot_1m_s1","bb_upper","bb_middle","bb_lower","bb_pct_b","bb_width_pct",
        ];
        if (extraCols.includes(sortCol)) {
          sortCol = "realistic_yield";
          sortDir = "desc";
          document.querySelectorAll("#results-table th").forEach(h =>
            h.classList.remove("sort-asc", "sort-desc")
          );
        }
      }
      applyFilters();
    });

    // Sidebar filters
    $("filter-ticker").addEventListener("input", applyFilters);
    $("filter-flagged-only").addEventListener("change", applyFilters);

    $("filter-min-yield").addEventListener("input", () => {
      $("filter-min-yield-val").textContent = $("filter-min-yield").value + "%";
      applyFilters();
    });
    $("filter-max-delta").addEventListener("input", () => {
      $("filter-max-delta-val").textContent = $("filter-max-delta").value;
      applyFilters();
    });
    [$("filter-dte-min"), $("filter-dte-max")].forEach(inp =>
      inp.addEventListener("change", applyFilters)
    );

    // Alpaca settings modal
    $("alpaca-settings-btn").addEventListener("click", openAlpacaSettings);
    $("alpaca-modal-close").addEventListener("click", () => $("alpaca-modal-overlay").classList.add("hidden"));
    $("alpaca-save-btn").addEventListener("click", saveAlpacaCredentials);
    $("alpaca-clear-btn").addEventListener("click", clearAlpacaCredentials);
    $("alpaca-modal-overlay").addEventListener("click", e => {
      if (e.target === $("alpaca-modal-overlay")) $("alpaca-modal-overlay").classList.add("hidden");
    });
    // "Set up credentials" link in panel placeholder
    $("alpaca-connect-link")?.addEventListener("click", openAlpacaSettings);

    // Trade review modal
    $("trade-modal-close").addEventListener("click", () => {
      $("trade-modal-overlay").classList.add("hidden");
      _pendingTradeRow = null;
    });
    $("trade-cancel-btn").addEventListener("click", () => {
      $("trade-modal-overlay").classList.add("hidden");
      _pendingTradeRow = null;
    });
    $("trade-confirm-btn").addEventListener("click", submitOrder);
    $("trade-modal-overlay").addEventListener("click", e => {
      if (e.target === $("trade-modal-overlay")) {
        $("trade-modal-overlay").classList.add("hidden");
        _pendingTradeRow = null;
      }
    });

    // Alpaca refresh button
    $("alpaca-refresh-btn").addEventListener("click", loadAlpacaAccount);

    // If already connected, show tabs + trade col + load account
    if (isAlpacaConnected()) {
      document.querySelectorAll(".tab-alpaca").forEach(t => t.classList.remove("hidden"));
      document.querySelectorAll(".alpaca-col").forEach(el => el.classList.remove("hidden"));
      loadAlpacaAccount();
    } else {
      $("alpaca-panel").classList.remove("hidden");
      renderAlpacaPlaceholder();
    }

    // Load latest on startup
    fetch("/api/results/latest")
      .then(r => r.json())
      .then(data => {
        if (!data.error) {
          allRows = data.results || [];
          updateKPIs(data);
          syncSidebarDte(data);
          applyFilters();   // also refreshes the chart from filteredRows
          const ts = data.scan_time || "";
          if (ts) {
            $("last-scan-time").textContent = "Last scan: " + ts;
            $("kpi-scan-time").textContent  = "Scanned " + ts;
          }
        }
      })
      .catch(() => {});

    loadScanHistory();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
