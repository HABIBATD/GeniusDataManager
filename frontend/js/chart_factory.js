/**
 * chart_factory.js — Chart.js wrapper for GeniusDataManager Stage 4
 *
 * Builds Chart.js chart instances from a ChartSpec + PipelineResult.
 * Relies on Chart.js 4.x loaded globally via CDN.
 *
 * Exports:
 *   buildChart(spec, pipelineResult) → HTMLCanvasElement | null
 */

// ── Shared palette ────────────────────────────────────────────────────────────
const PALETTE = [
  'rgba(124,  58, 237, 0.85)',  // purple
  'rgba( 59, 130, 246, 0.85)',  // blue
  'rgba( 16, 185, 129, 0.85)',  // green
  'rgba(245, 158,  11, 0.85)',  // amber
  'rgba(239,  68,  68, 0.85)',  // red
  'rgba(236,  72, 153, 0.85)',  // pink
  'rgba( 20, 184, 166, 0.85)',  // teal
  'rgba(249, 115,  22, 0.85)',  // orange
];
const PALETTE_BORDER = PALETTE.map(c => c.replace('0.85', '1'));

const CHART_DEFAULTS = {
  responsive: true,
  maintainAspectRatio: true,
  animation: { duration: 600, easing: 'easeOutQuart' },
  plugins: {
    legend: {
      labels: {
        color: '#A1A1AA',
        font: { family: "'Inter', sans-serif", size: 11 },
        padding: 16,
        boxWidth: 12,
        boxHeight: 12,
      },
    },
    tooltip: {
      backgroundColor: '#1A1A2E',
      borderColor: '#27272A',
      borderWidth: 1,
      titleColor: '#FFFFFF',
      bodyColor: '#A1A1AA',
      padding: 12,
      callbacks: {
        label: ctx => {
          const v = ctx.parsed?.y ?? ctx.parsed;
          if (typeof v === 'number')
            return ` ${ctx.dataset.label || ''}: ${v.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
          return ` ${ctx.dataset.label}: ${v}`;
        },
      },
    },
  },
  scales: {
    x: {
      grid: { color: 'rgba(255,255,255,0.05)' },
      ticks: { color: '#71717A', font: { size: 10 } },
    },
    y: {
      grid: { color: 'rgba(255,255,255,0.05)' },
      ticks: {
        color: '#71717A',
        font: { size: 10 },
        callback: v => v.toLocaleString(),
      },
    },
  },
};


/**
 * Build a Chart.js chart from a ChartSpec.
 * @param {object} spec - ChartSpec from the LayoutPlan
 * @param {object} result - PipelineResult from the upload endpoint
 * @returns {HTMLElement|null}  A <div class="chart-canvas-wrap"> containing the canvas
 */
export function buildChart(spec, result) {
  if (!result.stage1 || !result.stage2) return null;

  const rawTable = result.stage1.tables[spec.table_index];
  const tp = result.stage2.table_profiles[spec.table_index];
  if (!rawTable || !tp) return null;

  const { labels, datasets } = _extractData(spec, rawTable, tp);
  if (!labels.length || !datasets.length) return null;

  const wrap = document.createElement('div');
  wrap.className = 'chart-canvas-wrap';

  const canvas = document.createElement('canvas');
  canvas.id = `canvas_${spec.chart_id}`;
  wrap.appendChild(canvas);

  const config = _buildConfig(spec.chart_type, labels, datasets);
  if (!config) return null;

  new Chart(canvas, config);  // eslint-disable-line no-new
  return wrap;
}


// ── Data extraction ───────────────────────────────────────────────────────────

function _extractData(spec, rawTable, tp) {
  const headers = rawTable.headers;
  const rows = rawTable.rows;
  const roles = tp.row_roles || rows.map(() => 'detail');

  // Filter rows by spec.row_filter
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
  // For time series: x = category column labels (row descriptions), y = time period columns
  const xColIdx = spec.x_col ? headers.indexOf(spec.x_col) : 0;
  const yCols = spec.y_cols;  // these are the time-period column headers

  // Labels = time period headers (columns), datasets = one per category row
  const yColIndices = yCols.map(h => headers.indexOf(h)).filter(i => i >= 0);

  if (!yColIndices.length) return { labels: [], datasets: [] };

  const labels = yColIndices.map(i => headers[i]);

  // One dataset per row (up to 8 for readability)
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
      tension: 0.4,
      pointRadius: 4,
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

  // Labels = x column values (row categories, up to 24)
  const maxRows = 24;
  const pairs = filteredPairs.slice(0, maxRows);
  const labels = pairs.map(([row]) => {
    if (xColIdx >= 0 && xColIdx < row.cells.length)
      return String(row.cells[xColIdx].value ?? '—');
    return `Row ${row.row_index}`;
  });

  // One dataset per y column
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
      borderRadius: 4,
    };
  });

  return { labels, datasets };
}


// ── Chart.js config builders ─────────────────────────────────────────────────

function _buildConfig(chartType, labels, datasets) {
  const base = JSON.parse(JSON.stringify(CHART_DEFAULTS));  // deep clone

  switch (chartType) {
    case 'line':
    case 'area':
      if (chartType === 'area' && datasets[0]) {
        datasets[0].fill = true;
        datasets[0].backgroundColor = datasets[0].backgroundColor?.replace('0.85', '0.15') ?? 'rgba(124,58,237,0.15)';
      }
      return { type: 'line', data: { labels, datasets }, options: base };

    case 'bar_horizontal':
      base.indexAxis = 'y';
      base.scales = {
        x: { ...base.scales.x, ticks: { ...base.scales.x.ticks, callback: v => v.toLocaleString() } },
        y: { ...base.scales.y, ticks: { ...base.scales.y.ticks } },
      };
      return { type: 'bar', data: { labels, datasets }, options: base };

    case 'grouped_bar':
      return { type: 'bar', data: { labels, datasets }, options: base };

    default:
      return null;
  }
}
