/**
 * dashboard.js
 * ------------
 * Interactive Plotly.js Visual Representation & Executive Analytics Engine.
 * 
 * Features:
 *   - Dark & Light mode dynamic theme engine
 *   - Glassmorphic KPI cards with monospace typography
 *   - Categorized Data Quality transformation badges
 *   - Dual Distribution cards (Histogram + 1.5x IQR Box Plot)
 *   - Diverging Pearson correlation heatmap & strongest pairs ranking
 *   - Real-time numerical distribution search & filter
 *   - Executive Gemini AI Briefing with 1-click clipboard copy
 *   - Section tab switcher for seamless navigation
 */

(function (global) {
  "use strict";

  // Dynamic Theme Palette Generator
  function getTheme() {
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    return {
      isDark,
      ink: isDark ? "#f1f5f9" : "#0f172a",
      muted: isDark ? "#94a3b8" : "#64748b",
      accent: isDark ? "#818cf8" : "#4f46e5",
      accentSecondary: isDark ? "#38bdf8" : "#0284c7",
      accentGradient: isDark ? ["#818cf8", "#38bdf8"] : ["#4f46e5", "#0284c7"],
      warm: isDark ? "#fbbf24" : "#d97706",
      warmLight: isDark ? "rgba(251, 191, 36, 0.15)" : "rgba(217, 119, 6, 0.12)",
      grid: isDark ? "#1e293b" : "#e2e8f0",
      line: isDark ? "#334155" : "#cbd5e1",
      surface: isDark ? "#111827" : "#ffffff",
      surfaceAlt: isDark ? "#1e293b" : "#f8fafc",
      cardBorder: isDark ? "#1f293d" : "#e2e8f0",
    };
  }

  const PLOT_CONFIG = {
    responsive: true,
    displaylogo: false,
    displayModeBar: false,
  };

  function getBaseLayout() {
    const t = getTheme();
    return {
      font: { family: "'Plus Jakarta Sans', system-ui, sans-serif", size: 12, color: t.ink },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      margin: { l: 50, r: 16, t: 10, b: 40 },
    };
  }

  // Helper DOM and Formatting Functions
  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function fmt(val, digits = 2) {
    if (val === null || val === undefined) return "–";
    if (typeof val !== "number") return String(val);
    if (Number.isInteger(val)) return val.toLocaleString();
    return val.toLocaleString(undefined, { maximumFractionDigits: digits });
  }

  function plot(node, data, layout) {
    if (typeof Plotly === "undefined") {
      node.innerHTML = '<div class="empty">Plotly.js library not loaded.</div>';
      return;
    }
    Plotly.newPlot(node, data, { ...getBaseLayout(), ...layout }, PLOT_CONFIG);
  }

  function emptyMsg(node, text) {
    node.innerHTML = `<div class="empty-state">${text || "No data available."}</div>`;
  }

  // Markdown renderer for Gemini AI Insights
  function renderMarkdown(mdText) {
    if (!mdText) return "";
    let html = mdText
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/^### (.*$)/gim, '<h4 class="ai-heading-3">$1</h4>')
      .replace(/^## (.*$)/gim, '<h3 class="ai-heading-2">$1</h3>')
      .replace(/^# (.*$)/gim, '<h2 class="ai-heading-1">$1</h2>')
      .replace(/^\> (.*$)/gim, '<blockquote class="ai-quote">$1</blockquote>')
      .replace(/\*\*(.*?)\*\*/g, '<strong class="ai-bold">$1</strong>')
      .replace(/\*(.*?)\*/g, "<em>$1</em>")
      .replace(/^\s*[-*]\s+(.*$)/gim, '<li class="ai-item">$1</li>')
      .replace(/`([^`]+)`/g, '<code class="ai-code">$1</code>');

    html = html.replace(/(<li class="ai-item">[\s\S]*?<\/li>)+/g, '<ul class="ai-list">$&</ul>');

    const paragraphs = html.split(/\n{2,}/);
    return paragraphs
      .map(p => {
        p = p.trim();
        if (!p) return "";
        if (p.startsWith("<h") || p.startsWith("<ul") || p.startsWith("<block")) {
          return p;
        }
        return `<p class="ai-p">${p.replace(/\n/g, "<br>")}</p>`;
      })
      .join("");
  }

  // 1. Overview KPI Tiles
  function renderOverviewTiles(overview, quality, container) {
    container.innerHTML = "";
    const missingTotal = (quality.missing_before_cleaning || []).reduce((a, r) => a + (r.missing || 0), 0);

    const tiles = [
      { label: "Total Rows", val: fmt(overview.rows), sub: `Started with ${fmt(overview.original_rows || overview.rows)}`, icon: "📄", color: "indigo" },
      { label: "Features", val: overview.columns, sub: `${overview.numerical_columns} num · ${overview.categorical_columns} cat`, icon: "📊", color: "cyan" },
      { label: "Missing Cells", val: fmt(missingTotal), sub: quality.imputed?.length ? `${quality.imputed.length} col(s) imputed` : "Complete records", icon: "🩹", color: "amber" },
      { label: "Duplicates Cleaned", val: fmt(quality.duplicates_removed || 0), sub: `${fmt(quality.duplicates_found || 0)} detected`, icon: "🧹", color: "emerald" },
      { label: "Memory Footprint", val: `${fmt(overview.memory_kb, 1)} KB`, sub: `${overview.datetime_columns || 0} datetime cols`, icon: "⚡", color: "violet" },
    ];

    tiles.forEach(t => {
      const card = el("div", `kpi-card kpi-${t.color}`);
      card.innerHTML = `
        <div class="kpi-header">
          <span class="kpi-icon">${t.icon}</span>
          <span class="kpi-label">${t.label}</span>
        </div>
        <div class="kpi-value">${t.val}</div>
        <div class="kpi-sub">${t.sub}</div>
      `;
      container.appendChild(card);
    });
  }

  // 2. Data Quality: Missing Values Chart
  function renderMissingChart(quality, container) {
    container.innerHTML = "";
    const t = getTheme();
    const rows = (quality.missing_before_cleaning || [])
      .filter(r => r.missing > 0)
      .sort((a, b) => a.missing_pct - b.missing_pct);

    if (!rows.length) {
      container.innerHTML = `
        <div class="quality-clean-box">
          <div class="clean-icon">✨</div>
          <div class="clean-title">100% Complete Dataset</div>
          <div class="clean-desc">No missing values or sparse columns were detected in this dataset.</div>
        </div>
      `;
      return;
    }

    plot(container, [{
      type: "bar",
      orientation: "h",
      x: rows.map(r => r.missing_pct),
      y: rows.map(r => r.column),
      customdata: rows.map(r => r.missing),
      hovertemplate: "<b>%{y}</b><br>%{x:.1f}% missing (%{customdata} rows)<extra></extra>",
      marker: {
        color: t.warm,
        line: { color: t.isDark ? "#78350f" : "#b45309", width: 1 },
      },
    }], {
      height: Math.max(200, rows.length * 34 + 60),
      margin: { l: 140, r: 24, t: 8, b: 40 },
      xaxis: { title: "% Missing Values", gridcolor: t.grid, range: [0, Math.max(100, ...rows.map(r => r.missing_pct)) * 1.05] },
      yaxis: { gridcolor: t.grid },
    });
  }

  // 3. Data Quality: Cleaning Log Badges
  function renderCleaningLog(quality, container) {
    container.innerHTML = "";
    const logContainer = el("div", "cleaning-log-grid");

    const badges = [];
    if (quality.duplicates_removed > 0) {
      badges.push({
        type: "success",
        tag: "DUPLICATES REMOVED",
        text: `Removed ${fmt(quality.duplicates_removed)} identical duplicate row(s) to guarantee record uniqueness.`,
      });
    } else {
      badges.push({
        type: "neutral",
        tag: "NO DUPLICATES",
        text: "Zero duplicate rows found; all records are distinct.",
      });
    }

    if (quality.imputed && quality.imputed.length) {
      quality.imputed.forEach(i => {
        badges.push({
          type: "warning",
          tag: "IMPUTATION",
          text: `Filled ${fmt(i.count)} missing values in "${i.column}" using ${i.strategy} strategy (${fmt(i.value)}).`,
        });
      });
    }

    if (quality.converted_types && Object.keys(quality.converted_types).length) {
      Object.entries(quality.converted_types).forEach(([col, typ]) => {
        badges.push({
          type: "info",
          tag: "TYPE CONVERTED",
          text: `Inferred text column "${col}" as numeric/datetime and standardized type.`,
        });
      });
    }

    if (quality.dropped_columns && quality.dropped_columns.length) {
      badges.push({
        type: "danger",
        tag: "DROPPED COLUMNS",
        text: `Removed sparse columns with excessive missingness: ${quality.dropped_columns.join(", ")}.`,
      });
    }

    if (quality.renamed_columns && Object.keys(quality.renamed_columns).length) {
      Object.entries(quality.renamed_columns).forEach(([oldN, newN]) => {
        badges.push({
          type: "neutral",
          tag: "SANITIZED HEADER",
          text: `Cleaned whitespace: "${oldN}" → "${newN}".`,
        });
      });
    }

    badges.forEach(b => {
      const item = el("div", `log-badge-item badge-${b.type}`);
      item.innerHTML = `
        <span class="badge-tag">${b.tag}</span>
        <span class="badge-text">${b.text}</span>
      `;
      logContainer.appendChild(item);
    });

    container.appendChild(logContainer);
  }

  // 4. Column Types Inventory
  function renderColumnTypes(columnTypes, container) {
    container.innerHTML = "";
    const groups = [
      { label: "Numerical Features", cols: columnTypes.numerical || [], icon: "🔢", color: "indigo" },
      { label: "Categorical Features", cols: columnTypes.categorical || [], icon: "🏷️", color: "cyan" },
      { label: "Datetime Features", cols: columnTypes.datetime || [], icon: "📅", color: "violet" },
    ];

    const grid = el("div", "types-inventory-grid");
    groups.forEach(g => {
      const box = el("div", `type-group-card group-${g.color}`);
      box.innerHTML = `
        <div class="type-group-header">
          <span class="type-icon">${g.icon}</span>
          <span class="type-title">${g.label}</span>
          <span class="type-count-pill">${g.cols.length}</span>
        </div>
      `;
      const chips = el("div", "chips-wrap");
      if (!g.cols.length) {
        chips.innerHTML = '<span class="chip-empty">None detected</span>';
      } else {
        g.cols.forEach(c => {
          const chip = el("span", "data-chip", c);
          chips.appendChild(chip);
        });
      }
      box.appendChild(chips);
      grid.appendChild(box);
    });
    container.appendChild(grid);
  }

  // 5. Numerical Summary Table
  function renderNumericalSummaryTable(numericStats, container) {
    container.innerHTML = "";
    const cols = Object.keys(numericStats || {});
    if (!cols.length) {
      emptyMsg(container, "No numerical columns available for aggregation.");
      return;
    }

    const table = el("table", "modern-table");
    const thead = el("thead");
    const hr = el("tr");
    ["Column", "Count", "Mean", "Median", "Mode", "Std Dev", "Min", "Max", "Skew", "Outliers"].forEach(h => {
      hr.appendChild(el("th", null, h));
    });
    thead.appendChild(hr);
    table.appendChild(thead);

    const tbody = el("tbody");
    cols.forEach(c => {
      const s = numericStats[c];
      const row = el("tr");
      const modeStr = (s.mode && s.mode.length) ? s.mode.map(m => fmt(m)).join(", ") : "–";
      const outlierPill = s.outlier_count > 0 
        ? `<span class="pill-outlier">${fmt(s.outlier_count)}</span>` 
        : '<span class="pill-zero">0</span>';

      row.innerHTML = `
        <td><strong>${c}</strong></td>
        <td class="mono">${fmt(s.count)}</td>
        <td class="mono">${fmt(s.mean)}</td>
        <td class="mono">${fmt(s.median)}</td>
        <td class="mono">${modeStr}</td>
        <td class="mono">${fmt(s.std)}</td>
        <td class="mono">${fmt(s.min)}</td>
        <td class="mono">${fmt(s.max)}</td>
        <td class="mono">${fmt(s.skew)}</td>
        <td>${outlierPill}</td>
      `;
      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    container.appendChild(table);
  }

  // 6. Distributions: Dual Histogram + Box Plot per Numeric Feature
  function renderDistributions(numericStats, container) {
    container.innerHTML = "";
    const t = getTheme();
    const cols = Object.keys(numericStats || {});
    if (!cols.length) {
      emptyMsg(container, "No numerical features to display.");
      return;
    }

    // Filter search input
    const filterBar = el("div", "dist-filter-bar");
    filterBar.innerHTML = `
      <div class="search-input-wrap">
        <span class="search-icon">🔍</span>
        <input type="text" id="dist-search" class="search-input" placeholder="Filter numerical features (e.g. Age, Income)...">
      </div>
      <span class="dist-count-badge" id="dist-count-badge">Showing ${cols.length} feature(s)</span>
    `;
    container.appendChild(filterBar);

    const cardsGrid = el("div", "dist-grid");
    container.appendChild(cardsGrid);

    cols.forEach(col => {
      const s = numericStats[col];
      const h = s.histogram;
      if (!h || !h.counts || !h.counts.length) return;

      const card = el("div", "dist-card");
      card.setAttribute("data-col-name", col.toLowerCase());

      card.innerHTML = `
        <div class="dist-card-header">
          <div class="dist-title-wrap">
            <h3 class="dist-title">${col}</h3>
            <span class="dist-outlier-tag ${s.outlier_count > 0 ? "tag-has-outliers" : "tag-clean"}">
              ${s.outlier_count > 0 ? `⚠️ ${fmt(s.outlier_count)} Outliers` : "✓ Clean Range"}
            </span>
          </div>
          <div class="dist-stats-pills">
            <span>Mean: <b>${fmt(s.mean)}</b></span>
            <span>Median: <b>${fmt(s.median)}</b></span>
            <span>Std: <b>${fmt(s.std)}</b></span>
          </div>
        </div>
        <div class="plot-box hist-plot-node"></div>
        <div class="plot-box box-plot-node"></div>
      `;
      cardsGrid.appendChild(card);

      const histNode = card.querySelector(".hist-plot-node");
      const boxNode = card.querySelector(".box-plot-node");

      const centers = h.counts.map((_, i) => (h.edges[i] + h.edges[i + 1]) / 2);
      const widths = h.counts.map((_, i) => h.edges[i + 1] - h.edges[i]);

      // Histogram
      plot(histNode, [{
        type: "bar",
        x: centers,
        y: h.counts,
        width: widths,
        customdata: h.counts.map((_, i) => [h.edges[i], h.edges[i + 1]]),
        hovertemplate: "Range: <b>%{customdata[0]:.4g} – %{customdata[1]:.4g}</b><br>Count: <b>%{y} rows</b><extra></extra>",
        marker: {
          color: t.accent,
          line: { color: t.isDark ? "#1e1b4b" : "#ffffff", width: 1 },
        },
      }], {
        height: 180,
        bargap: 0,
        margin: { l: 45, r: 16, t: 8, b: 32 },
        xaxis: { gridcolor: t.grid },
        yaxis: { title: "Rows", gridcolor: t.grid },
      });

      // Aligned 1.5x IQR Box Plot
      plot(boxNode, [{
        type: "box",
        orientation: "h",
        y: [""],
        q1: [s.q1],
        median: [s.median],
        q3: [s.q3],
        lowerfence: [s.whisker_low],
        upperfence: [s.whisker_high],
        mean: [s.mean],
        sd: [s.std === null ? 0 : s.std],
        boxmean: "sd",
        marker: { color: t.warm },
        line: { color: t.warm, width: 2 },
        fillcolor: t.warmLight,
        hoverinfo: "x",
      }], {
        height: 80,
        margin: { l: 45, r: 16, t: 2, b: 24 },
        xaxis: { gridcolor: t.grid, zeroline: false },
        yaxis: { showticklabels: false },
        showlegend: false,
      });
    });

    // Real-time distribution search listener
    const searchInput = filterBar.querySelector("#dist-search");
    const countBadge = filterBar.querySelector("#dist-count-badge");
    searchInput.addEventListener("input", (e) => {
      const q = e.target.value.toLowerCase().trim();
      const allCards = cardsGrid.querySelectorAll(".dist-card");
      let visible = 0;
      allCards.forEach(c => {
        const name = c.getAttribute("data-col-name") || "";
        if (!q || name.includes(q)) {
          c.style.display = "block";
          visible++;
        } else {
          c.style.display = "none";
        }
      });
      countBadge.textContent = `Showing ${visible} of ${cols.length} feature(s)`;
    });
  }

  // 7. Correlation Heatmap & Ranked Pairs
  function renderCorrelation(correlation, heatContainer, pairsContainer) {
    heatContainer.innerHTML = "";
    pairsContainer.innerHTML = "";
    const t = getTheme();

    if (!correlation || !correlation.columns || correlation.columns.length < 2) {
      emptyMsg(heatContainer, "Requires at least two numerical columns with variance.");
      emptyMsg(pairsContainer, "–");
      return;
    }

    // Heatmap
    plot(heatContainer, [{
      type: "heatmap",
      z: correlation.matrix,
      x: correlation.columns,
      y: correlation.columns,
      zmin: -1,
      zmax: 1,
      zmid: 0,
      colorscale: [
        [0.0, t.warm],
        [0.5, t.isDark ? "#1e293b" : "#f8fafc"],
        [1.0, t.accent],
      ],
      texttemplate: "%{z:.2f}",
      hovertemplate: "<b>%{y} × %{x}</b><br>Pearson r = <b>%{z:.3f}</b><extra></extra>",
      colorbar: { thickness: 12, title: "r" },
    }], {
      height: Math.max(340, correlation.columns.length * 44 + 90),
      margin: { l: 110, r: 16, t: 10, b: 90 },
      yaxis: { autorange: "reversed", gridcolor: t.grid },
      xaxis: { tickangle: -30, gridcolor: t.grid },
    });

    // Strongest Pairs Table
    if (!correlation.top_pairs || !correlation.top_pairs.length) {
      emptyMsg(pairsContainer, "No strong pairwise correlations detected.");
      return;
    }

    const table = el("table", "modern-table");
    const thead = el("thead");
    const tr = el("tr");
    ["Feature Pair", "Pearson r", "Strength", "Direction"].forEach(h => tr.appendChild(el("th", null, h)));
    thead.appendChild(tr);
    table.appendChild(thead);

    const tbody = el("tbody");
    correlation.top_pairs.forEach(p => {
      const row = el("tr");
      const strengthBadge = p.strength === "very strong" 
        ? '<span class="pill-strong">Very Strong</span>'
        : p.strength === "strong"
        ? '<span class="pill-moderate">Strong</span>'
        : `<span class="pill-weak">${p.strength}</span>`;

      const dirIcon = p.direction === "positive" ? "↗ Positive" : "↘ Negative";

      row.innerHTML = `
        <td><strong>${p.a}</strong> × <strong>${p.b}</strong></td>
        <td class="mono font-bold">${p.r.toFixed(3)}</td>
        <td>${strengthBadge}</td>
        <td>${dirIcon}</td>
      `;
      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    pairsContainer.appendChild(table);
  }

  // 8. Categorical Frequencies
  function renderCategoricals(categoricalStats, container) {
    container.innerHTML = "";
    const t = getTheme();
    const cols = Object.keys(categoricalStats || {});
    if (!cols.length) {
      emptyMsg(container, "No categorical features present.");
      return;
    }

    const grid = el("div", "cat-grid");
    container.appendChild(grid);

    cols.forEach(c => {
      const s = categoricalStats[c];
      const isId = s.likely_identifier;

      const card = el("div", "cat-card");
      card.innerHTML = `
        <div class="cat-card-header">
          <div class="cat-title-wrap">
            <h3 class="cat-title">${c}</h3>
            <span class="cat-badge ${isId ? "badge-id" : "badge-cat"}">
              ${isId ? "High Cardinality (ID)" : `${fmt(s.unique)} Categories`}
            </span>
          </div>
          <div class="cat-subnote">Most common: <b>${(s.mode || []).join(", ") || "–"}</b></div>
        </div>
        <div class="cat-chart-node"></div>
      `;
      grid.appendChild(card);

      const chartNode = card.querySelector(".cat-chart-node");

      if (isId || !s.top_frequency || !s.top_frequency.length) {
        chartNode.innerHTML = `
          <div class="id-notice-box">
            <span>🔑</span>
            <div>Unique identifier column. Frequency bar charts are omitted to maintain performance.</div>
          </div>
        `;
        return;
      }

      const rows = s.top_frequency.slice().reverse();
      const labels = rows.map(r => (r.value.length > 22 ? r.value.slice(0, 21) + "…" : r.value));

      plot(chartNode, [{
        type: "bar",
        orientation: "h",
        x: rows.map(r => r.count),
        y: labels,
        customdata: rows.map(r => [r.value, r.pct]),
        hovertemplate: "<b>%{customdata[0]}</b><br>%{x} rows (%{customdata[1]}%)<extra></extra>",
        marker: {
          color: t.accent,
          line: { color: t.isDark ? "#312e81" : "#4338ca", width: 1 },
        },
      }], {
        height: Math.max(160, rows.length * 28 + 50),
        margin: { l: 120, r: 24, t: 6, b: 34 },
        xaxis: { title: "Count", gridcolor: t.grid },
        yaxis: { gridcolor: t.grid },
      });

      if (s.other_count > 0) {
        card.appendChild(el("div", "cat-other-note", `+ ${fmt(s.other_count)} additional occurrences spread across remaining classes.`));
      }
    });
  }

  // 9. AI Insights Renderer with 1-Click Copy
  function renderAiInsights(insights, container) {
    container.innerHTML = "";
    if (!insights) {
      container.innerHTML = `
        <div class="ai-pending-box">
          <div class="ai-sparkle-icon">✨</div>
          <div class="ai-pending-title">AI Briefing Ready to Generate</div>
          <p>Add your Gemini API key in the options bar or .env to generate live contextual reasoning and strategic executive takeaways.</p>
        </div>
      `;
      return;
    }

    const header = el("div", "ai-briefing-header");
    header.innerHTML = `
      <div class="ai-model-tag">
        <span class="ai-glow-dot"></span>
        <span>Google Gemini Analytical Synthesis</span>
      </div>
      <button class="btn-copy-ai" id="btn-copy-insights" title="Copy to clipboard">
        <span id="copy-icon">📋</span> <span id="copy-text">Copy Report</span>
      </button>
    `;
    container.appendChild(header);

    const body = el("div", "ai-briefing-body");
    body.innerHTML = renderMarkdown(insights);
    container.appendChild(body);

    // Setup Copy Button
    const copyBtn = header.querySelector("#btn-copy-insights");
    const copyIcon = header.querySelector("#copy-icon");
    const copyText = header.querySelector("#copy-text");

    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(insights);
        copyIcon.textContent = "✓";
        copyText.textContent = "Copied!";
        copyBtn.classList.add("copied");
        setTimeout(() => {
          copyIcon.textContent = "📋";
          copyText.textContent = "Copy Report";
          copyBtn.classList.remove("copied");
        }, 2200);
      } catch (err) {
        copyText.textContent = "Press Ctrl+C to copy";
      }
    });
  }

  // Setup Modern Tab Navigation
  function setupTabs(root) {
    const tabBtns = root.querySelectorAll(".nav-tab-btn");
    const panels = root.querySelectorAll(".dash-tab-panel");

    tabBtns.forEach(btn => {
      btn.addEventListener("click", () => {
        const targetTab = btn.getAttribute("data-tab");
        tabBtns.forEach(b => b.classList.remove("active"));
        btn.classList.add("active");

        if (targetTab === "all") {
          panels.forEach(p => p.classList.add("visible"));
        } else {
          panels.forEach(p => {
            if (p.id === `tab-${targetTab}`) {
              p.classList.add("visible");
            } else {
              p.classList.remove("visible");
            }
          });
        }

        // Trigger resize on visible plots
        window.dispatchEvent(new Event("resize"));
      });
    });
  }

  // Auto-build DOM skeleton with Tab Navigation
  function ensureDashboardDOM(root) {
    if (root.querySelector("#dash-tiles") || document.getElementById("dash-tiles")) {
      return;
    }

    root.innerHTML = `
      <div class="dash-hero-card">
        <div class="dash-meta-row">
          <div>
            <h1 id="dash-title" class="dash-main-title">Dataset Profiling Report</h1>
            <p id="dash-subtitle" class="dash-sub-title"></p>
          </div>
          <div class="dash-badge-cluster">
            <span class="meta-tag tag-ready">✓ Analysis Complete</span>
          </div>
        </div>
        <div class="tiles-grid" id="dash-tiles"></div>
      </div>

      <!-- Interactive Tab Bar -->
      <nav class="dash-tab-nav">
        <button class="nav-tab-btn active" data-tab="ai">✨ Executive AI Insights</button>
        <button class="nav-tab-btn" data-tab="quality">🛡️ Data Quality</button>
        <button class="nav-tab-btn" data-tab="stats">📊 Summary Table</button>
        <button class="nav-tab-btn" data-tab="dist">📈 Distributions</button>
        <button class="nav-tab-btn" data-tab="corr">🔗 Correlations</button>
        <button class="nav-tab-btn" data-tab="cat">🏷️ Categoricals</button>
        <button class="nav-tab-btn" data-tab="all">📑 View All Sections</button>
      </nav>

      <!-- Tab 1: AI Insights -->
      <section class="dash-tab-panel visible" id="tab-ai">
        <div class="card card-ai-box">
          <div class="card-top-bar">
            <span class="card-icon-badge">✨</span>
            <div class="card-titles">
              <h2>Executive AI Synthesis & Actionable Recommendations</h2>
              <p class="card-sub">Contextual data science briefing generated by Google Gemini.</p>
            </div>
          </div>
          <div id="dash-insights"></div>
        </div>
      </section>

      <!-- Tab 2: Data Quality -->
      <section class="dash-tab-panel" id="tab-quality">
        <div class="split-cards-grid">
          <div class="card">
            <div class="card-top-bar">
              <span class="card-icon-badge">🩹</span>
              <div class="card-titles">
                <h2>Missing Values Profile</h2>
                <p class="card-sub">Pre-cleaning missingness percentage across all features.</p>
              </div>
            </div>
            <div id="dash-missing-chart"></div>
          </div>
          <div class="card">
            <div class="card-top-bar">
              <span class="card-icon-badge">🛡️</span>
              <div class="card-titles">
                <h2>Preprocessing & Hygiene Log</h2>
                <p class="card-sub">Audited transformations, duplicate purges, and imputations.</p>
              </div>
            </div>
            <div id="dash-cleaning-log"></div>
          </div>
        </div>
        <div class="card mt-4">
          <div class="card-top-bar">
            <span class="card-icon-badge">📑</span>
            <div class="card-titles">
              <h2>Feature Schema Inventory</h2>
              <p class="card-sub">Detected data types and categorical assignments.</p>
            </div>
          </div>
          <div id="dash-types"></div>
        </div>
      </section>

      <!-- Tab 3: Numerical Statistics -->
      <section class="dash-tab-panel" id="tab-stats">
        <div class="card">
          <div class="card-top-bar">
            <span class="card-icon-badge">📊</span>
            <div class="card-titles">
              <h2>Numerical Aggregations & Distribution Metrics</h2>
              <p class="card-sub">Central tendency, variance, skewness, and IQR fence outliers.</p>
            </div>
          </div>
          <div class="scroll-table-box" id="dash-stats-table"></div>
        </div>
      </section>

      <!-- Tab 4: Distributions -->
      <section class="dash-tab-panel" id="tab-dist">
        <div class="card">
          <div class="card-top-bar">
            <span class="card-icon-badge">📈</span>
            <div class="card-titles">
              <h2>Feature Distributions & 1.5× IQR Outliers</h2>
              <p class="card-sub">Auto-binned frequency histograms aligned with horizontal box plots.</p>
            </div>
          </div>
          <div id="dash-distributions"></div>
        </div>
      </section>

      <!-- Tab 5: Correlation -->
      <section class="dash-tab-panel" id="tab-corr">
        <div class="split-cards-grid">
          <div class="card">
            <div class="card-top-bar">
              <span class="card-icon-badge">🔗</span>
              <div class="card-titles">
                <h2>Pearson Correlation Heatmap</h2>
                <p class="card-sub">Pairwise linear correlation (-1.0 to +1.0).</p>
              </div>
            </div>
            <div id="dash-corr-heatmap"></div>
          </div>
          <div class="card">
            <div class="card-top-bar">
              <span class="card-icon-badge">🏆</span>
              <div class="card-titles">
                <h2>Ranked Feature Relationships</h2>
                <p class="card-sub">Strongest pairwise associations and driving relationships.</p>
              </div>
            </div>
            <div class="scroll-table-box" id="dash-corr-pairs"></div>
          </div>
        </div>
      </section>

      <!-- Tab 6: Categoricals -->
      <section class="dash-tab-panel" id="tab-cat">
        <div class="card">
          <div class="card-top-bar">
            <span class="card-icon-badge">🏷️</span>
            <div class="card-titles">
              <h2>Categorical Class Distributions</h2>
              <p class="card-sub">Frequency counts, class percentages, and cardinality alerts.</p>
            </div>
          </div>
          <div id="dash-categoricals"></div>
        </div>
      </section>
    `;

    setupTabs(root);
  }

  // Master Dashboard Render Entrypoint
  function renderDashboard(data, targetContainer) {
    if (!data) return;

    let root = typeof targetContainer === "string" ? document.getElementById(targetContainer) : targetContainer;
    if (!root) {
      root = document.querySelector("main") || document.body;
    }

    ensureDashboardDOM(root);

    const getEl = (dashId, fallbackId) => document.getElementById(dashId) || document.getElementById(fallbackId);

    const titleEl = getEl("dash-title", "title");
    const subtitleEl = getEl("dash-subtitle", "subtitle");
    const tilesEl = getEl("dash-tiles", "tiles");
    const missingEl = getEl("dash-missing-chart", "missing-chart");
    const logEl = getEl("dash-cleaning-log", "cleaning-log");
    const typesEl = getEl("dash-types", "types");
    const statsEl = getEl("dash-stats-table", "stats-table");
    const distEl = getEl("dash-distributions", "distributions");
    const heatEl = getEl("dash-corr-heatmap", "corr-heatmap");
    const pairsEl = getEl("dash-corr-pairs", "corr-pairs");
    const catEl = getEl("dash-categoricals", "categoricals");
    const insightsEl = getEl("dash-insights", "insights");

    const o = data.overview || {};
    const q = data.data_quality || {};

    if (titleEl) titleEl.textContent = data.title || "Dataset Analysis";
    if (subtitleEl) {
      subtitleEl.textContent = `${fmt(o.rows)} rows × ${o.columns} columns analyzed (${fmt(o.original_rows)} initial rows, ${fmt(q.duplicates_removed || 0)} duplicates removed).`;
    }

    if (tilesEl) renderOverviewTiles(o, q, tilesEl);
    if (missingEl) renderMissingChart(q, missingEl);
    if (logEl) renderCleaningLog(q, logEl);
    if (typesEl) renderColumnTypes(data.column_types || {}, typesEl);
    if (statsEl) renderNumericalSummaryTable(data.numeric_stats || {}, statsEl);
    if (distEl) renderDistributions(data.numeric_stats || {}, distEl);
    if (heatEl && pairsEl) renderCorrelation(data.correlation || {}, heatEl, pairsEl);
    if (catEl) renderCategoricals(data.categorical_stats || {}, catEl);
    if (insightsEl) renderAiInsights(data.insights, insightsEl);
  }

  // Resize handler
  window.addEventListener("resize", function () {
    if (typeof Plotly === "undefined") return;
    const plots = document.querySelectorAll(".js-plotly-plot");
    plots.forEach(p => {
      try {
        Plotly.Plots.resize(p);
      } catch (e) {}
    });
  });

  const DataLensDashboard = {
    renderDashboard,
    renderOverviewTiles,
    renderMissingChart,
    renderCleaningLog,
    renderColumnTypes,
    renderNumericalSummaryTable,
    renderDistributions,
    renderCorrelation,
    renderCategoricals,
    renderAiInsights,
    renderMarkdown,
    fmt,
  };

  global.DataLensDashboard = DataLensDashboard;
  global.renderDashboard = renderDashboard;

  if (typeof module !== "undefined" && module.exports) {
    module.exports = DataLensDashboard;
  }
})(typeof window !== "undefined" ? window : this);
