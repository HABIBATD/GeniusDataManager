/**
 * chart_factory.js — Dynamic Chart.js wrapper for GeniusDataManager
 *
 * Supports:
 *   - Line & Area Charts
 *   - Vertical & Horizontal Bar Charts
 *   - Doughnut & Pie Charts
 *   - Interactive in-card chart type switching
 */

// ── Shared palette ────────────────────────────────────────────────────────────
const PALETTE = [
  'rgba(99,  102, 241, 0.85)',  // indigo
  'rgba(139,  92, 246, 0.85)',  // violet
  'rgba(  6, 182, 212, 0.85)',  // cyan
  'rgba( 16, 185, 129, 0.85)',  // emerald
  'rgba(245, 158,  11, 0.85)',  // amber
  'rgba(239,  68,  68, 0.85)',  // red
  'rgba(236,  72, 153, 0.85)',  // pink
  'rgba(249, 115,  22, 0.85)',  // orange
];
const PALETTE_BORDER = PALETTE.map(c => c.replace('0.85', '1'));

const CHART_DEFAULTS = {
  responsive: true,
  maintainAspectRatio: true,
  animation: { duration: 500, easing: 'easeOutQuart' },
  plugins: {
    legend: {
      labels: {
        color: '#94A3B8',
        font: { family: "'Inter', sans-serif", size: 11 },
        padding: 14,
        boxWidth: 12,
        boxHeight: 12,
      },
    },
    tooltip: {
      backgroundColor: '#111420',
      borderColor: 'rgba(99, 102, 241, 0.25)',
      borderWidth: 1,
      titleColor: '#FFFFFF',
      bodyColor: '#94A3B8',
      padding: 12,
      callbacks: {
        label: ctx => {
          const v = ctx.parsed?.y ?? ctx.parsed?.x ?? ctx.parsed;
          if (typeof v === 'number')
            return ` ${ctx.dataset.label || ctx.label || ''}: ${v.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
          return ` ${ctx.dataset.label || ctx.label || ''}: ${v}`;
        },
      },
    },
  },
  scales: {
    x: {
      grid: { color: 'rgba(255,255,255,0.04)' },
      ticks: { color: '#64748B', font: { size: 10 } },
    },
    y: {
      grid: { color: 'rgba(255,255,255,0.04)' },
      ticks: {
        color: '#64748B',
        font: { size: 10 },
        callback: v => typeof v === 'number' ? v.toLocaleString() : v,
      },
    },
  },
};


/**
 * Build a Chart.js chart container with an interactive chart-type switcher.
 */
export function buildChart(spec, result) {
  if (!result.stage1 || !result.stage2) return null;

  const rawTable = result.stage1.tables[spec.table_index];
  const tp = result.stage2.table_profiles[spec.table_index];
  if (!rawTable || !tp) return null;

  const { labels, datasets } = _extractData(spec, rawTable, tp);
  if (!labels.length || !datasets.length) return null;

  const container = document.createElement('div');
  container.className = 'chart-container-inner';

  // ── Chart Type Switcher Toolbar ──
  const toolbar = document.createElement('div');
  toolbar.className = 'chart-toolbar';

  const types = [
    { id: 'bar', label: '📊 Bar' },
    { id: 'line', label: '📈 Line' },
    { id: 'area', label: '📉 Area' },
    { id: 'doughnut', label: '🍩 Donut' },
  ];

  let currentType = spec.chart_type;
  if (currentType === 'grouped_bar' || currentType === 'bar_horizontal') currentType = 'bar';

  const wrap = document.createElement('div');
  wrap.className = 'chart-canvas-wrap';

  const canvas = document.createElement('canvas');
  canvas.id = `canvas_${spec.chart_id}`;
  wrap.appendChild(canvas);

  let chartInstance = null;

  function renderChart(type) {
    if (chartInstance) {
      chartInstance.destroy();
    }
    const config = _buildConfig(type, labels, datasets);
    if (config) {
      chartInstance = new Chart(canvas, config);
    }
  }

  types.forEach(t => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `btn-chart-type ${t.id === currentType ? 'active' : ''}`;
    btn.textContent = t.label;
    btn.addEventListener('click', () => {
      toolbar.querySelectorAll('.btn-chart-type').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderChart(t.id);
    });
    toolbar.appendChild(btn);
  });

  container.appendChild(toolbar);
  container.appendChild(wrap);

  renderChart(currentType);
  return container;
}


// ── Data extraction ───────────────────────────────────────────────────────────

function _extractData(spec, rawTable, tp) {
  const headers = rawTable.headers;
  const rows = rawTable.rows;
  const roles = tp.row_roles || rows.map(() => 'detail');

  const filteredPairs = rows
    .map((r, i) => [r, roles[i]])
    .filter(([, role]) => {
      if (spec.row_filter === 'detail') return role === 'detail';
      if (spec.row_filter === 'subtotal') return ['subtotal', 'grand_total'].includes(role);
      return true;
    });

  if (spec.chart_type === 'line' || spec.chart_type === 'area') {
    return _extractTimeSeriesData(spec, headers, filteredPairs);
  }
  return _extractCategoryData(spec, headers, filteredPairs);
}


function _extractTimeSeriesData(spec, headers, filteredPairs) {
  const xColIdx = spec.x_col ? headers.indexOf(spec.x_col) : 0;
  const yCols = spec.y_cols;
  const yColIndices = yCols.map(h => headers.indexOf(h)).filter(i => i >= 0);

  if (!yColIndices.length) return { labels: [], datasets: [] };

  const labels = yColIndices.map(i => headers[i]);
  const maxSeries = 8;
  const datasets = filteredPairs.slice(0, maxSeries).map(([row], si) => {
    const label = xColIdx >= 0 && xColIdx < row.cells.length
      ? String(row.cells[xColIdx].value || `Row ${row.row_index}`)
      : `Row ${row.row_index}`;

    const data = yColIndices.map(ci => {
      if (ci >= row.cells.length) return null;
      const v = row.cells[ci].value;
      return typeof v === 'number' ? v : (parseFloat(v) || null);
    });

    const color = PALETTE[si % PALETTE.length];
    return {
      label,
      data,
      borderColor: PALETTE_BORDER[si % PALETTE.length],
      backgroundColor: color,
      tension: 0.35,
      pointRadius: 3,
      pointHoverRadius: 6,
      fill: false,
      borderWidth: 2,
    };
  });

  return { labels, datasets };
}


function _extractCategoryData(spec, headers, filteredPairs) {
  const xColIdx = spec.x_col ? headers.indexOf(spec.x_col) : 0;
  const yCols = spec.y_cols;
  const yColIndices = yCols.map(h => headers.indexOf(h)).filter(i => i >= 0);

  if (!yColIndices.length || !filteredPairs.length) return { labels: [], datasets: [] };

  const maxRows = 24;
  const pairs = filteredPairs.slice(0, maxRows);
  const labels = pairs.map(([row]) => {
    if (xColIdx >= 0 && xColIdx < row.cells.length)
      return String(row.cells[xColIdx].value ?? '—');
    return `Row ${row.row_index}`;
  });

  const datasets = yColIndices.map((ci, si) => {
    const data = pairs.map(([row]) => {
      if (ci >= row.cells.length) return null;
      const v = row.cells[ci].value;
      return typeof v === 'number' ? v : (parseFloat(v) || null);
    });
    const color = PALETTE[si % PALETTE.length];
    return {
      label: headers[ci],
      data,
      backgroundColor: color,
      borderColor: PALETTE_BORDER[si % PALETTE.length],
      borderWidth: 1,
      borderRadius: 5,
    };
  });

  return { labels, datasets };
}


// ── Chart.js config builders ─────────────────────────────────────────────────

function _buildConfig(chartType, labels, datasets) {
  const base = JSON.parse(JSON.stringify(CHART_DEFAULTS));

  // Deep clone datasets so mutations don't bleed between types
  const clonedDatasets = datasets.map(d => ({ ...d }));

  switch (chartType) {
    case 'line':
      clonedDatasets.forEach(d => {
        d.fill = false;
        d.tension = 0.35;
        d.pointRadius = 4;
        d.borderWidth = 2;
      });
      return { type: 'line', data: { labels, datasets: clonedDatasets }, options: base };

    case 'area':
      clonedDatasets.forEach((d, i) => {
        d.fill = true;
        d.tension = 0.35;
        d.backgroundColor = PALETTE[i % PALETTE.length].replace('0.85', '0.2');
        d.borderColor = PALETTE_BORDER[i % PALETTE.length];
        d.borderWidth = 2;
      });
      return { type: 'line', data: { labels, datasets: clonedDatasets }, options: base };

    case 'bar_horizontal':
      base.indexAxis = 'y';
      return { type: 'bar', data: { labels, datasets: clonedDatasets }, options: base };

    case 'bar':
    case 'grouped_bar':
      return { type: 'bar', data: { labels, datasets: clonedDatasets }, options: base };

    case 'doughnut':
    case 'pie': {
      // For doughnut/pie, use the first metric series across all categories
      const firstSeries = clonedDatasets[0] || { data: [] };
      const sliceColors = labels.map((_, i) => PALETTE[i % PALETTE.length]);
      const donutData = {
        labels,
        datasets: [{
          label: firstSeries.label || 'Value',
          data: firstSeries.data,
          backgroundColor: sliceColors,
          borderColor: '#111420',
          borderWidth: 2,
        }],
      };
      const donutOptions = {
        responsive: true,
        maintainAspectRatio: true,
        plugins: base.plugins,
      };
      return { type: chartType, data: donutData, options: donutOptions };
    }

    default:
      return { type: 'bar', data: { labels, datasets: clonedDatasets }, options: base };
  }
}
