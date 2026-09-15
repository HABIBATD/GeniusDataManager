/**
 * UI Component builders for GeniusDataManager.
 */

// Active Chart.js instances registry to destroy before re-rendering
const activeCharts = {};

export function renderSchemaTable(columns, previewRows) {
  const container = document.getElementById('schema-table-container');
  if (!container) return;

  let html = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Column Name</th>
          <th>Inferred Dtype</th>
          <th>Semantic Tag</th>
          <th>Null %</th>
          <th>Unique Count</th>
          <th>Sample Values</th>
        </tr>
      </thead>
      <tbody>
  `;

  columns.forEach(col => {
    const samples = (col.sample_values || []).slice(0, 3).map(v => `<span class="pill">${v}</span>`).join(' ');
    html += `
      <tr>
        <td style="font-weight: 600;">${escapeHtml(col.name)}</td>
        <td><span class="badge badge-dtype">${escapeHtml(col.dtype)}</span></td>
        <td><span class="badge badge-semantic">${escapeHtml(col.semantic_label || 'text')}</span></td>
        <td><span class="badge badge-null">${col.null_pct}%</span></td>
        <td>${col.unique_count.toLocaleString()}</td>
        <td>${samples || '<span style="color:var(--text-dim)">-</span>'}</td>
      </tr>
    `;
  });

  html += '</tbody></table>';
  container.innerHTML = html;
}

export function renderMappingRows(columns) {
  const container = document.getElementById('mapping-rows-container');
  if (!container) return;

  let html = `
    <table class="data-table">
      <thead>
        <tr>
          <th style="width: 50px;">Keep</th>
          <th>Source Column</th>
          <th>Target Field Name</th>
          <th>Target Type Coercion</th>
        </tr>
      </thead>
      <tbody>
  `;

  columns.forEach((col, idx) => {
    const targetName = suggestTargetName(col.name);
    html += `
      <tr class="mapping-row" data-source="${escapeHtml(col.name)}">
        <td>
          <input type="checkbox" class="mapping-keep-check" id="keep_col_${idx}" checked style="width: 18px; height: 18px; cursor: pointer;">
        </td>
        <td style="font-weight: 600;">${escapeHtml(col.name)}</td>
        <td>
          <input type="text" class="form-input mapping-target-input" value="${escapeHtml(targetName)}" placeholder="target_field_name">
        </td>
        <td>
          <select class="form-select mapping-type-select">
            <option value="string" ${col.dtype === 'string' ? 'selected' : ''}>string</option>
            <option value="int" ${col.dtype === 'int' ? 'selected' : ''}>int</option>
            <option value="float" ${col.dtype === 'float' ? 'selected' : ''}>float</option>
            <option value="datetime" ${col.dtype === 'datetime' ? 'selected' : ''}>datetime</option>
            <option value="currency" ${col.semantic_label === 'currency' ? 'selected' : ''}>currency</option>
            <option value="boolean" ${col.dtype === 'boolean' ? 'selected' : ''}>boolean</option>
          </select>
        </td>
      </tr>
    `;
  });

  html += '</tbody></table>';
  container.innerHTML = html;
}

export function renderFilterRow(columns) {
  const container = document.getElementById('filter-rules-list');
  if (!container) return;

  const rowId = 'filter_rule_' + Date.now() + '_' + Math.random().toString(36).substr(2, 4);
  const div = document.createElement('div');
  div.className = 'filter-row';
  div.id = rowId;

  let colOptions = columns.map(c => `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name)}</option>`).join('');

  div.innerHTML = `
    <select class="form-select filter-col-select">
      ${colOptions}
    </select>
    <select class="form-select filter-op-select">
      <option value="equals">equals</option>
      <option value="not_equals">not equals</option>
      <option value="contains">contains</option>
      <option value="range">range (min..max)</option>
      <option value="in_list">in list (comma sep)</option>
      <option value="not_null">is not null</option>
    </select>
    <input type="text" class="form-input filter-val-input" placeholder="Value or min..max">
    <button type="button" class="btn btn-danger btn-sm" onclick="document.getElementById('${rowId}').remove()" title="Remove filter">✕</button>
  `;

  container.appendChild(div);
}

export function renderKPICards(kpis) {
  const container = document.getElementById('kpi-cards-grid');
  if (!container) return;

  if (!kpis || kpis.length === 0) {
    container.innerHTML = '';
    return;
  }

  let html = '';
  kpis.forEach(kpi => {
    let changeBadge = '';
    if (kpi.change_pct !== null && kpi.change_pct !== undefined) {
      const isPos = kpi.change_pct >= 0;
      const cls = isPos ? 'positive' : 'negative';
      const icon = isPos ? '↑' : '↓';
      changeBadge = `<span class="kpi-change ${cls}">${icon} ${Math.abs(kpi.change_pct)}%</span>`;
    }

    html += `
      <div class="kpi-card">
        <div class="kpi-label">${escapeHtml(kpi.label)} ${changeBadge}</div>
        <div class="kpi-value">${escapeHtml(String(kpi.formatted || kpi.value))}</div>
        <div class="kpi-subtext">${escapeHtml(kpi.subtext || '')}</div>
      </div>
    `;
  });

  container.innerHTML = html;
}

export function renderCharts(chartsData) {
  const container = document.getElementById('charts-grid');
  if (!container) return;

  // Destroy previous charts
  Object.keys(activeCharts).forEach(key => {
    if (activeCharts[key]) {
      activeCharts[key].destroy();
      delete activeCharts[key];
    }
  });

  if (!chartsData || chartsData.length === 0) {
    container.innerHTML = '<div style="color:var(--text-muted)">No charts generated for this analysis.</div>';
    return;
  }

  container.innerHTML = '';

  chartsData.forEach((chartObj, idx) => {
    const cardDiv = document.createElement('div');
    cardDiv.className = 'chart-card';

    const canvasId = `chart_canvas_${idx}_${Date.now()}`;
    cardDiv.innerHTML = `
      <div style="font-family:'Outfit',sans-serif; font-weight:700; font-size:1.1rem; margin-bottom:16px;">
        ${escapeHtml(chartObj.title)}
      </div>
      <div class="chart-container">
        <canvas id="${canvasId}"></canvas>
      </div>
    `;

    container.appendChild(cardDiv);

    // Initialize Chart.js
    const ctx = document.getElementById(canvasId).getContext('2d');
    const colors = ['#6366f1', '#06b6d4', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6'];

    const datasets = (chartObj.series || []).map((s, sIdx) => {
      const color = colors[sIdx % colors.length];
      const isPie = chartObj.chart_type === 'pie' || chartObj.chart_type === 'doughnut';
      return {
        label: s.name,
        data: s.data,
        backgroundColor: isPie ? colors : color + 'aa',
        borderColor: isPie ? '#0f172a' : color,
        borderWidth: 2,
        tension: 0.3,
        fill: chartObj.chart_type === 'line' ? false : true,
      };
    });

    activeCharts[canvasId] = new window.Chart(ctx, {
      type: chartObj.chart_type === 'line' ? 'line' : (chartObj.chart_type === 'doughnut' ? 'doughnut' : 'bar'),
      data: {
        labels: chartObj.labels || [],
        datasets: datasets,
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            labels: { color: '#94a3b8', font: { family: 'Inter' } }
          },
          tooltip: {
            backgroundColor: '#1e293b',
            titleColor: '#f8fafc',
            bodyColor: '#cbd5e1',
            borderColor: 'rgba(255,255,255,0.1)',
            borderWidth: 1,
          }
        },
        scales: (chartObj.chart_type === 'doughnut' || chartObj.chart_type === 'pie') ? {} : {
          x: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.05)' } },
          y: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.05)' } }
        }
      }
    });
  });
}

export function renderAlignedPreviewTable(alignedPreview, columns) {
  const container = document.getElementById('aligned-table-container');
  if (!container) return;

  if (!alignedPreview || alignedPreview.length === 0) {
    container.innerHTML = '<div style="color:var(--text-muted)">No rows to display.</div>';
    return;
  }

  const cols = columns || Object.keys(alignedPreview[0]);

  let html = `
    <table class="data-table">
      <thead>
        <tr>
          ${cols.map(c => `<th>${escapeHtml(c)}</th>`).join('')}
        </tr>
      </thead>
      <tbody>
  `;

  alignedPreview.forEach(row => {
    html += '<tr>';
    cols.forEach(c => {
      const val = row[c];
      html += `<td>${val !== null && val !== undefined ? escapeHtml(String(val)) : '<span style="color:var(--text-dim)">null</span>'}</td>`;
    });
    html += '</tr>';
  });

  html += '</tbody></table>';
  container.innerHTML = html;
}

function suggestTargetName(name) {
  return name.trim().toLowerCase().replace(/[\s\-\/\.]+/g, '_').replace(/[^a-z0-9_]/g, '');
}

function escapeHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
