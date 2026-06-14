/**
 * Performance Analytics & Trade Journal UI
 *
 * Follows ui-ux-patterns:
 * - Semantic HTML
 * - ARIA labels for accessibility
 * - Responsive design (mobile-first)
 * - Event delegation
 * - Proper Chart.js cleanup
 *
 * Reference: .claude/referenced-skills/ui-ux-patterns/
 */

// Chart instances for proper cleanup
const chartInstances = {};

/**
 * Format number as currency
 * @param {number} value
 * @returns {string}
 */
function formatCurrency(value) {
  if (value === null || value === undefined) return '$0.00';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(value);
}

/**
 * Format number as percentage
 * @param {number} value
 * @param {number} decimals
 * @returns {string}
 */
function formatPercent(value, decimals = 2) {
  if (value === null || value === undefined) return '0.00%';
  return (value).toFixed(decimals) + '%';
}

/**
 * Destroy any existing chart instance to prevent conflicts
 * @param {string} chartId
 */
function destroyChart(chartId) {
  if (chartInstances[chartId]) {
    chartInstances[chartId].destroy();
    delete chartInstances[chartId];
  }
}

// =========================================================================
// Trade Journal Tab
// =========================================================================

/**
 * Load and display all trades
 */
async function loadTradeJournal() {
  try {
    const response = await fetch('/api/trades');
    if (!response.ok) {
      showError('Failed to load trades');
      return;
    }

    const data = await response.json();
    if (data.error) {
      showError(data.error);
      return;
    }

    renderTradeJournal(data.trades || []);
  } catch (error) {
    console.error('Error loading trades:', error);
    showError('Failed to load trades');
  }
}

/**
 * Sync trades from Alpaca
 */
async function syncAlpacaTrades() {
  try {
    // Get Alpaca credentials from localStorage
    const alpacaKey = localStorage.getItem('alpaca_key');
    const alpacaSecret = localStorage.getItem('alpaca_secret');

    if (!alpacaKey || !alpacaSecret) {
      showError('Alpaca credentials not found. Set them in settings first.');
      return;
    }

    // Show loading state
    const syncBtn = document.querySelector('[onclick="syncAlpacaTrades()"]');
    if (syncBtn) {
      syncBtn.disabled = true;
      syncBtn.textContent = '⏳ Syncing...';
    }

    const response = await fetch('/api/trades/sync-alpaca?days_back=90', {
      method: 'POST',
      headers: {
        'X-APCA-Key': alpacaKey,
        'X-APCA-Secret': alpacaSecret,
        'Content-Type': 'application/json',
      },
    });

    const data = await response.json();

    // Restore button state
    if (syncBtn) {
      syncBtn.disabled = false;
      syncBtn.textContent = '🔄 Sync from Alpaca';
    }

    if (!response.ok) {
      showError(data.error || 'Failed to sync trades');
      return;
    }

    // Show success message
    showSuccess(data.message || `Synced ${data.synced} trades from Alpaca`);

    // Reload trade journal and performance
    loadTradeJournal();
    loadPerformance();

  } catch (error) {
    console.error('Error syncing trades:', error);
    showError('Failed to sync with Alpaca');

    // Restore button state
    const syncBtn = document.querySelector('[onclick="syncAlpacaTrades()"]');
    if (syncBtn) {
      syncBtn.disabled = false;
      syncBtn.textContent = '🔄 Sync from Alpaca';
    }
  }
}

/**
 * Render trade journal table
 * @param {Array} trades
 */
function renderTradeJournal(trades) {
  const container = document.getElementById('trade-journal-container');
  if (!container) return;

  if (!trades || trades.length === 0) {
    container.innerHTML = `
      <div class="empty-state" role="status" aria-label="No trades">
        <p>No trades recorded yet.</p>
        <div class="empty-actions">
          <button class="btn-primary" onclick="syncAlpacaTrades()" aria-label="Sync trades from Alpaca">
            🔄 Sync from Alpaca
          </button>
          <button class="btn-primary" onclick="showTradeForm()" aria-label="Create new trade">
            ➕ New Trade
          </button>
        </div>
      </div>
    `;
    return;
  }

  // Calculate stats
  const openTrades = trades.filter(t => t.status === 'open').length;
  const closedTrades = trades.filter(t => t.status === 'closed').length;
  const totalPnL = trades.reduce((sum, t) => sum + (t.realized_pnl || 0), 0);
  const winRate = closedTrades > 0
    ? ((trades.filter(t => t.status === 'closed' && t.realized_pnl > 0).length / closedTrades) * 100)
    : 0;

  // Build stats row
  const statsHtml = `
    <div class="trade-stats" role="region" aria-label="Trade statistics">
      <div class="stat-box">
        <label>Total Trades</label>
        <span class="stat-value">${trades.length}</span>
      </div>
      <div class="stat-box">
        <label>Open</label>
        <span class="stat-value" style="color: #ff9500;">${openTrades}</span>
      </div>
      <div class="stat-box">
        <label>Closed</label>
        <span class="stat-value" style="color: #4CAF50;">${closedTrades}</span>
      </div>
      <div class="stat-box">
        <label>Win Rate</label>
        <span class="stat-value" style="color: ${winRate > 65 ? '#4CAF50' : '#ff5722'};">
          ${formatPercent(winRate, 1)}
        </span>
      </div>
      <div class="stat-box">
        <label>Total P&L</label>
        <span class="stat-value" style="color: ${totalPnL > 0 ? '#4CAF50' : '#ff5722'};">
          ${formatCurrency(totalPnL)}
        </span>
      </div>
      <div class="stat-box" style="grid-column: span 1; display: flex; flex-direction: column; justify-content: center;">
        <button class="btn-small" onclick="syncAlpacaTrades()" aria-label="Sync trades from Alpaca">
          🔄 Sync Alpaca
        </button>
      </div>
    </div>
  `;

  // Build trades table
  const tableHtml = `
    <table class="trades-table" role="grid" aria-label="Trade journal">
      <thead>
        <tr role="row">
          <th role="columnheader">Symbol</th>
          <th role="columnheader">Entry Date</th>
          <th role="columnheader">Strike</th>
          <th role="columnheader">Premium</th>
          <th role="columnheader">Status</th>
          <th role="columnheader">P&L</th>
          <th role="columnheader">ROI</th>
          <th role="columnheader"></th>
        </tr>
      </thead>
      <tbody>
        ${trades.map(t => `
          <tr role="row" class="trade-row" data-trade-id="${t.id}">
            <td role="gridcell"><strong>${t.symbol}</strong></td>
            <td role="gridcell">${new Date(t.entry_date).toLocaleDateString()}</td>
            <td role="gridcell">$${t.strike.toFixed(2)}</td>
            <td role="gridcell">$${t.premium_received.toFixed(2)}</td>
            <td role="gridcell">
              <span class="status-badge" style="background: ${t.status === 'open' ? '#ff9500' : '#4CAF50'};">
                ${t.status.toUpperCase()}
              </span>
            </td>
            <td role="gridcell" style="color: ${t.realized_pnl > 0 ? '#4CAF50' : '#ff5722'};">
              ${formatCurrency(t.realized_pnl || 0)}
            </td>
            <td role="gridcell">
              ${t.roi_percent !== null ? formatPercent(t.roi_percent * 100, 2) : '—'}
            </td>
            <td role="gridcell">
              <button class="btn-small" onclick="expandTrade('${t.id}')"
                      aria-label="Show details for ${t.symbol}">
                ⋯
              </button>
            </td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;

  container.innerHTML = statsHtml + tableHtml;
}

/**
 * Show expanded trade details
 * @param {string} tradeId
 */
function expandTrade(tradeId) {
  // TODO: Implement modal or expansion panel
  console.log('Expand trade:', tradeId);
}

// =========================================================================
// Performance Dashboard Tab
// =========================================================================

/**
 * Load and display performance metrics
 */
async function loadPerformance() {
  try {
    const [metricsResponse, monthlyResponse] = await Promise.all([
      fetch('/api/performance'),
      fetch('/api/performance/monthly'),
    ]);

    if (!metricsResponse.ok || !monthlyResponse.ok) {
      showError('Failed to load performance data');
      return;
    }

    const metricsData = await metricsResponse.json();
    const monthlyData = await monthlyResponse.json();

    if (metricsData.error || monthlyData.error) {
      showError('Failed to load performance data');
      return;
    }

    renderPerformanceDashboard(metricsData.metrics || {}, monthlyData.monthly || {});
  } catch (error) {
    console.error('Error loading performance:', error);
    showError('Failed to load performance data');
  }
}

/**
 * Render performance dashboard
 * @param {Object} metrics
 * @param {Object} monthly
 */
function renderPerformanceDashboard(metrics, monthly) {
  const container = document.getElementById('performance-container');
  if (!container) return;

  // Key metrics boxes
  const metricsHtml = `
    <section class="metrics-grid" role="region" aria-label="Performance metrics">
      <div class="metric-card">
        <h3>Win Rate</h3>
        <div class="metric-value" style="color: ${metrics.win_rate_pct > 65 ? '#4CAF50' : '#ff5722'};">
          ${formatPercent(metrics.win_rate_pct || 0, 1)}
        </div>
        <p class="metric-detail">${metrics.winning_trades || 0} of ${metrics.closed_trades || 0} trades</p>
      </div>

      <div class="metric-card">
        <h3>Average ROI</h3>
        <div class="metric-value" style="color: ${metrics.average_roi_pct > 2 ? '#4CAF50' : '#ff5722'};">
          ${formatPercent(metrics.average_roi_pct || 0, 2)}
        </div>
        <p class="metric-detail">Per trade return</p>
      </div>

      <div class="metric-card">
        <h3>Total P&L</h3>
        <div class="metric-value" style="color: ${metrics.total_realized_pnl > 0 ? '#4CAF50' : '#ff5722'};">
          ${formatCurrency(metrics.total_realized_pnl || 0)}
        </div>
        <p class="metric-detail">Cumulative profit/loss</p>
      </div>

      <div class="metric-card">
        <h3>Sharpe Ratio</h3>
        <div class="metric-value" style="color: ${metrics.sharpe_ratio > 1 ? '#4CAF50' : '#ff5722'};">
          ${(metrics.sharpe_ratio || 0).toFixed(2)}
        </div>
        <p class="metric-detail">Risk-adjusted return</p>
      </div>

      <div class="metric-card">
        <h3>Max Drawdown</h3>
        <div class="metric-value" style="color: #ff5722;">
          ${formatPercent(Math.abs(metrics.max_drawdown_pct || 0), 2)}
        </div>
        <p class="metric-detail">Worst peak-to-trough</p>
      </div>

      <div class="metric-card">
        <h3>Total Trades</h3>
        <div class="metric-value">${metrics.total_trades || 0}</div>
        <p class="metric-detail">${metrics.closed_trades || 0} closed</p>
      </div>
    </section>
  `;

  // Charts section
  const chartsHtml = `
    <section class="charts-section" role="region" aria-label="Performance charts">
      <div class="chart-container">
        <h3>Win/Loss Distribution</h3>
        <canvas id="winloss-chart" role="img" aria-label="Win loss distribution pie chart"></canvas>
      </div>

      <div class="chart-container">
        <h3>Monthly P&L</h3>
        <canvas id="monthly-pnl-chart" role="img" aria-label="Monthly profit and loss bar chart"></canvas>
      </div>

      <div class="chart-container">
        <h3>Cumulative P&L</h3>
        <canvas id="cumulative-pnl-chart" role="img" aria-label="Cumulative profit and loss line chart"></canvas>
      </div>
    </section>
  `;

  container.innerHTML = metricsHtml + chartsHtml;

  // Render charts
  renderWinLossChart(metrics);
  renderMonthlyPnLChart(monthly);
  renderCumulativePnLChart(monthly);
}

/**
 * Render win/loss pie chart
 * @param {Object} metrics
 */
function renderWinLossChart(metrics) {
  destroyChart('winloss-chart');

  const canvas = document.getElementById('winloss-chart');
  if (!canvas) return;

  const wins = metrics.winning_trades || 0;
  const losses = (metrics.closed_trades || 0) - wins;

  chartInstances['winloss-chart'] = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: ['Winning Trades', 'Losing Trades'],
      datasets: [{
        data: [wins, losses],
        backgroundColor: ['#4CAF50', '#ff5722'],
        borderColor: '#fff',
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            padding: 15,
            font: { size: 12 },
          },
        },
      },
    },
  });
}

/**
 * Render monthly P&L bar chart
 * @param {Object} monthly
 */
function renderMonthlyPnLChart(monthly) {
  destroyChart('monthly-pnl-chart');

  const canvas = document.getElementById('monthly-pnl-chart');
  if (!canvas) return;

  const months = Object.keys(monthly).sort();
  const pnlData = months.map(m => monthly[m].total_pnl || 0);
  const colors = pnlData.map(p => p > 0 ? '#4CAF50' : '#ff5722');

  chartInstances['monthly-pnl-chart'] = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: months,
      datasets: [{
        label: 'Monthly P&L',
        data: pnlData,
        backgroundColor: colors,
        borderRadius: 4,
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      indexAxis: 'x',
      plugins: {
        legend: {
          display: false,
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            callback: (value) => formatCurrency(value),
          },
        },
      },
    },
  });
}

/**
 * Render cumulative P&L line chart
 * @param {Object} monthly
 */
function renderCumulativePnLChart(monthly) {
  destroyChart('cumulative-pnl-chart');

  const canvas = document.getElementById('cumulative-pnl-chart');
  if (!canvas) return;

  const months = Object.keys(monthly).sort();
  let cumulative = 0;
  const cumulativeData = months.map(m => {
    cumulative += (monthly[m].total_pnl || 0);
    return cumulative;
  });

  chartInstances['cumulative-pnl-chart'] = new Chart(canvas, {
    type: 'line',
    data: {
      labels: months,
      datasets: [{
        label: 'Cumulative P&L',
        data: cumulativeData,
        borderColor: '#2196F3',
        backgroundColor: 'rgba(33, 150, 243, 0.1)',
        borderWidth: 2,
        fill: true,
        tension: 0.4,
        pointRadius: 4,
        pointBackgroundColor: '#2196F3',
        pointHoverRadius: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: {
          display: true,
          position: 'top',
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            callback: (value) => formatCurrency(value),
          },
        },
      },
    },
  });
}

// =========================================================================
// Strategy Analysis Tab
// =========================================================================

/**
 * Load strategy analysis
 * @param {string} breakdown
 */
async function loadStrategyAnalysis(breakdown = 'delta_band') {
  try {
    const response = await fetch(`/api/performance/by-strategy?breakdown=${breakdown}`);
    if (!response.ok) {
      showError('Failed to load strategy analysis');
      return;
    }

    const data = await response.json();
    if (data.error) {
      showError(data.error);
      return;
    }

    renderStrategyAnalysis(data.analysis || {}, breakdown);
  } catch (error) {
    console.error('Error loading strategy analysis:', error);
    showError('Failed to load strategy analysis');
  }
}

/**
 * Render strategy analysis
 * @param {Object} analysis
 * @param {string} breakdown
 */
function renderStrategyAnalysis(analysis, breakdown) {
  const container = document.getElementById('strategy-container');
  if (!container) return;

  if (!analysis || Object.keys(analysis).length === 0) {
    container.innerHTML = '<p>No data to analyze yet.</p>';
    return;
  }

  // Get display name based on breakdown type
  const getDisplayName = (key, type) => {
    if (type === 'delta_band') {
      const names = {
        'conservative': 'Conservative (|Δ| ≤ 0.15)',
        'standard': 'Standard (|Δ| 0.15-0.22)',
        'aggressive': 'Aggressive (|Δ| > 0.22)',
      };
      return names[key] || key;
    }
    if (type === 'dte_window') {
      const names = {
        'weekly': 'Weekly (1-7 DTE)',
        'short_term': 'Short-term (8-21 DTE)',
        'medium_term': 'Medium-term (22-45 DTE)',
        'long_term': 'Long-term (46+ DTE)',
      };
      return names[key] || key;
    }
    return key;
  };

  const analysisHtml = `
    <div class="strategy-breakdown" role="region" aria-label="Strategy analysis">
      <div class="breakdown-selector">
        <button onclick="loadStrategyAnalysis('delta_band')"
                class="btn-small ${breakdown === 'delta_band' ? 'active' : ''}"
                aria-label="Analyze by delta band">
          Delta Band
        </button>
        <button onclick="loadStrategyAnalysis('dte_window')"
                class="btn-small ${breakdown === 'dte_window' ? 'active' : ''}"
                aria-label="Analyze by DTE window">
          DTE Window
        </button>
        <button onclick="loadStrategyAnalysis('symbol')"
                class="btn-small ${breakdown === 'symbol' ? 'active' : ''}"
                aria-label="Analyze by symbol">
          By Symbol
        </button>
      </div>

      <table class="strategy-table" role="grid" aria-label="Strategy analysis">
        <thead>
          <tr role="row">
            <th role="columnheader">Category</th>
            <th role="columnheader">Trades</th>
            <th role="columnheader">Closed</th>
            <th role="columnheader">Win Rate</th>
            <th role="columnheader">Avg ROI</th>
            <th role="columnheader">Total P&L</th>
          </tr>
        </thead>
        <tbody>
          ${Object.entries(analysis).map(([key, data]) => `
            <tr role="row">
              <td role="gridcell"><strong>${getDisplayName(key, breakdown)}</strong></td>
              <td role="gridcell">${data.total_trades || 0}</td>
              <td role="gridcell">${data.closed_trades || 0}</td>
              <td role="gridcell" style="color: ${data.win_rate > 65 ? '#4CAF50' : '#ff5722'};">
                ${formatPercent(data.win_rate || 0, 1)}
              </td>
              <td role="gridcell" style="color: ${data.avg_roi > 2 ? '#4CAF50' : '#ff5722'};">
                ${formatPercent(data.avg_roi || 0, 2)}
              </td>
              <td role="gridcell" style="color: ${data.total_pnl > 0 ? '#4CAF50' : '#ff5722'};">
                ${formatCurrency(data.total_pnl || 0)}
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;

  container.innerHTML = analysisHtml;
}

// =========================================================================
// Trade Entry Form
// =========================================================================

/**
 * Show trade entry form
 */
function showTradeForm() {
  // TODO: Open modal with trade entry form
  console.log('Show trade form');
}

/**
 * Submit new trade
 */
async function submitTrade(formData) {
  try {
    const response = await fetch('/api/trades', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData),
    });

    const data = await response.json();

    if (!response.ok) {
      showError(data.error || 'Failed to create trade');
      return;
    }

    showSuccess('Trade created successfully');
    loadTradeJournal();
    loadPerformance();
  } catch (error) {
    console.error('Error creating trade:', error);
    showError('Failed to create trade');
  }
}

// =========================================================================
// Initialization
// =========================================================================

/**
 * Initialize performance dashboard
 */
function initPerformanceDashboard() {
  // Get all tab buttons
  const tabs = document.querySelectorAll('.tab');

  tabs.forEach(tab => {
    tab.addEventListener('click', function() {
      const tabType = this.getAttribute('data-tab');

      // Load appropriate content based on tab
      if (tabType === 'journal') {
        loadTradeJournal();
      } else if (tabType === 'performance') {
        loadPerformance();
      } else if (tabType === 'strategy') {
        loadStrategyAnalysis('delta_band');
      }
    });
  });

  // Cleanup on page unload
  window.addEventListener('beforeunload', () => {
    Object.keys(chartInstances).forEach(key => {
      destroyChart(key);
    });
  });
}

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initPerformanceDashboard);
} else {
  initPerformanceDashboard();
}
