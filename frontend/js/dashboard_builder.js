/**
 * dashboard_builder.js — Stage 4 Dashboard Renderer
 *
 * Orchestrates the full dashboard render:
 *   1. POST /layout  (Stage 3 — get the LayoutPlan)
 *   2. Render export bar (Stage 5 trigger)
 *   3. Render layout notes card
 *   4. Render KPI strip
 *   5. Render charts grid (line / bar / grouped_bar via chart_factory.js)
 *   6. Render drilldown tables (via drilldown_table.js)
 *   7. Render mismatch panels (if any)
 *   8. Render anomaly panels (if any)
 *
 * Exports:
 *   renderDashboard(pipelineResult) → Promise<void>
 */

import { buildChart } from './chart_factory.js';
import { buildDrilldownTable } from './drilldown_table.js';
import { buildExportBar } from './export_trigger.js';

const API_BASE = '';  // same origin

/**
 * Render the Stage 4 dashboard for a completed pipeline result.
 * @param {object} pipelineResult  — full PipelineResult from /upload
 */
export async function renderDashboard(pipelineResult) {
  const section = document.getElementById('dashboard-section');
  const container = section.querySelector('.container') || section;
  container.innerHTML = '';

  // Show section
  section.classList.add('visible');
  section.scrollIntoView({ behavior: 'smooth', block: 'start' });

  // ── Loading state ────────────────────────────────────────────────────────
  const spinner = _el('div', { className: 'dashboard-spinner' });
  spinner.innerHTML = `<div class="spinner-ring"></div><span>Running Stage 3 — Layout Planning…</span>`;
  container.appendChild(spinner);

  // ── Stage 3: POST /layout ────────────────────────────────────────────────
  let layoutPlan;
  try {
    const resp = await fetch(`${API_BASE}/layout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: pipelineResult.task_id }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    layoutPlan = await resp.json();
  } catch (err) {
    container.innerHTML = `
      <div class="status-banner visible error">
        <span>❌ Stage 3 layout planning failed: ${escHtml(err.message)}</span>
      </div>`;
    return;
  }

  // ── Clear spinner, build dashboard ──────────────────────────────────────
  container.innerHTML = '';

  // Title
  container.appendChild(_el('div', { className: 'section-title' }, ['📈 Interactive Dashboard']));
  container.appendChild(_el('p', { className: 'section-subtitle' },
    [`${layoutPlan.charts.length} panel(s) auto-designed for "${pipelineResult.filename}"`]
  ));

  // Export bar
  container.appendChild(buildExportBar(pipelineResult.task_id));

  // Layout notes
  if (layoutPlan.layout_notes) {
    const notes = _el('div', { className: 'layout-notes-card' });
    notes.innerHTML = `<b>🧠 Layout Rationale:</b> ${escHtml(layoutPlan.layout_notes)}`;
    container.appendChild(notes);
  }

  // ── Charts grid ──────────────────────────────────────────────────────────
  const chartSpecs = layoutPlan.charts.filter(
    s => !['kpi', 'mismatch', 'anomaly'].includes(s.chart_type)
  );
  const specialSpecs = layoutPlan.charts.filter(
    s => ['mismatch', 'anomaly'].includes(s.chart_type)
  );
  const kpiSpec = layoutPlan.charts.find(s => s.chart_type === 'kpi');

  // KPI strip (always)
  if (kpiSpec) {
    container.appendChild(_buildKpiStrip(pipelineResult));
  }

  // Chart grid
  if (chartSpecs.length > 0) {
    const grid = _el('div', { className: 'dashboard-grid' });

    chartSpecs.forEach(spec => {
      const card = _buildChartCard(spec, pipelineResult);
      if (card) grid.appendChild(card);
    });

    container.appendChild(grid);
  }

  // ── Drilldown tables & Composer ──────────────────────────────────────────
  if (pipelineResult.stage1?.tables?.length > 0) {
    const dtHead = _el('h2', {
      style: 'margin: 40px 0 8px; font-size:1.15rem;',
    }, ['📋 Interactive Data Tables & Composer']);
    container.appendChild(dtHead);

    // If multiple tables, render the Consolidated Master View first!
    if (pipelineResult.stage1.tables.length > 1) {
      const composedDt = buildDrilldownTable(0, pipelineResult, { startOpen: true, isComposedView: true });
      container.appendChild(composedDt);
    }

    const indices = layoutPlan.drilldown_table_indices?.length ? layoutPlan.drilldown_table_indices : pipelineResult.stage1.tables.map((_, i) => i);
    for (const tidx of indices) {
      const dt = buildDrilldownTable(tidx, pipelineResult, { startOpen: pipelineResult.stage1.tables.length === 1 });
      container.appendChild(dt);
    }
  }

  // ── Special panels (mismatches, anomalies) ───────────────────────────────
  for (const spec of specialSpecs) {
    const panel = _buildSpecialPanel(spec, pipelineResult);
    if (panel) container.appendChild(panel);
  }
}


// ── KPI strip ─────────────────────────────────────────────────────────────────

function _buildKpiStrip(result) {
  const s2 = result.stage2;
  const kpis = [
    { icon: '📊', value: s2.total_tables,       label: 'Tables' },
    { icon: '🗂',  value: s2.total_detail_rows,  label: 'Detail Rows' },
    { icon: '🏷',  value: s2.total_categories,   label: 'Categories' },
    { icon: '🔍', value: s2.total_anomalies,    label: 'Anomalies',
      accent: s2.total_anomalies > 0 ? '#F87171' : null },
    { icon: '⚠️', value: s2.total_mismatches,   label: 'Mismatches',
      accent: s2.total_mismatches > 0 ? '#FBBF24' : null },
  ];

  const strip = _el('div', { className: 'kpi-strip' });
  kpis.forEach(k => {
    const card = _el('div', { className: 'kpi-card' });
    card.innerHTML = `
      <div style="font-size:1.4rem;margin-bottom:6px;">${k.icon}</div>
      <div class="kpi-value" style="${k.accent ? `color:${k.accent}` : ''}">${k.value}</div>
      <div class="kpi-label">${escHtml(k.label)}</div>
    `;
    strip.appendChild(card);
  });
  return strip;
}


// ── Chart card ────────────────────────────────────────────────────────────────

function _buildChartCard(spec, result) {
  const chartEl = buildChart(spec, result);
  if (!chartEl) return null;

  const card = _el('div', { className: 'chart-card' });

  // Icon per chart type
  const icons = { line: '📈', area: '📉', bar_horizontal: '📊', grouped_bar: '📊' };
  const icon = icons[spec.chart_type] || '📊';

  card.innerHTML = `
    <div class="chart-card-title">${icon} ${escHtml(spec.title)}</div>
    <div class="chart-card-notes">${escHtml(spec.notes)}</div>
  `;
  card.appendChild(chartEl);
  return card;
}


// ── Special panels (mismatch / anomaly) ───────────────────────────────────────

function _buildSpecialPanel(spec, result) {
  const tp = result.stage2?.table_profiles?.[spec.table_index];
  if (!tp) return null;

  if (spec.chart_type === 'mismatch') {
    return _buildMismatchPanel(spec, tp);
  }
  if (spec.chart_type === 'anomaly') {
    return _buildAnomalyPanel(spec, tp);
  }
  return null;
}

function _buildMismatchPanel(spec, tp) {
  const card = _el('div', { className: 'chart-card full-width', style: 'margin-top:20px;' });
  const count = tp.computed_column_mismatches?.length || 0;

  card.innerHTML = `
    <div class="chart-card-title">⚠️ ${escHtml(spec.title)}
      <span class="chip" style="background:rgba(245,158,11,0.15);color:#fbbf24;">${count}</span>
    </div>
    <div class="chart-card-notes">${escHtml(spec.notes)}</div>
  `;

  if (count === 0) {
    card.innerHTML += `<p style="color:var(--success);font-size:0.88rem;">✅ No computed column mismatches.</p>`;
    return card;
  }

  for (const m of tp.computed_column_mismatches) {
    const item = _el('div', { className: 'mismatch-item' });
    const delta = m.delta || 0;
    const sign = delta >= 0 ? '+' : '';
    const cls = delta < 0 ? 'neg' : 'pos';
    item.innerHTML = `
      <div style="font-weight:600;margin-bottom:8px;">
        Row: "${escHtml(m.row_description)}" — Col: "${escHtml(m.column_header)}"
      </div>
      <div class="mismatch-row">
        <div class="mismatch-val">
          <span class="mismatch-val-label">Source File Value</span>
          <span class="mismatch-val-num source">${fmt(m.source_value)}</span>
        </div>
        <div class="mismatch-val">
          <span class="mismatch-val-label">Our Recomputed Value</span>
          <span class="mismatch-val-num recomputed">${fmt(m.recomputed_value)}</span>
        </div>
        <div class="mismatch-val">
          <span class="mismatch-val-label">Delta</span>
          <span class="mismatch-val-num delta ${cls}">${sign}${fmt(delta)}</span>
        </div>
      </div>
      <div class="mismatch-formula">Recomputed from: ${escHtml(m.recomputed_from)}</div>
    `;
    card.appendChild(item);
  }
  return card;
}

function _buildAnomalyPanel(spec, tp) {
  const card = _el('div', { className: 'chart-card full-width', style: 'margin-top:20px;' });
  const count = tp.anomalies?.length || 0;

  card.innerHTML = `
    <div class="chart-card-title">🔍 ${escHtml(spec.title)}
      <span class="chip" style="background:rgba(239,68,68,0.15);color:#f87171;">${count}</span>
    </div>
    <div class="chart-card-notes">${escHtml(spec.notes)}</div>
  `;

  if (count === 0) {
    card.innerHTML += `<p style="color:var(--success);font-size:0.88rem;">✅ No anomalies detected.</p>`;
    return card;
  }

  const icons = {
    negative_in_positive_column: '🔴',
    blank_run: '🟡',
    ocr_corruption: '🔵',
    duplicate_row: '🟣',
  };

  for (const a of tp.anomalies) {
    const item = _el('div', { className: 'anomaly-item' });
    item.innerHTML = `
      <span class="anomaly-icon">${icons[a.anomaly_type] || '⚠️'}</span>
      <div class="anomaly-body">
        <div class="anomaly-type">${escHtml(a.anomaly_type.replace(/_/g, ' '))}</div>
        <div class="anomaly-desc">${escHtml(a.description)}</div>
      </div>
    `;
    card.appendChild(item);
  }
  return card;
}


// ── Helpers ───────────────────────────────────────────────────────────────────

function _el(tag, attrs = {}, children = []) {
  const e = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => {
    if (k === 'style' && typeof v === 'string') e.style.cssText = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else e[k] = v;
  });
  children.forEach(c => {
    if (typeof c === 'string') e.appendChild(document.createTextNode(c));
    else if (c instanceof Node) e.appendChild(c);
  });
  return e;
}

function escHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function fmt(n) {
  if (n === null || n === undefined) return '—';
  return Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
