/**
 * profile_viewer.js — Stage 2 Data Profile Display Module
 *
 * Renders the Stage 2 profile result into the #profile-section:
 *   1. Human-readable summary card (from stage2.human_summary)
 *   2. KPI strip (tables, rows, categories, anomalies, mismatches)
 *   3. Tab panel per detected table, each with:
 *      a. Column Profiles table (type, confidence, evidence, computed flag)
 *      b. Time Structure info (if detected)
 *      c. Anomalies panel (always visible, never hidden)
 *      d. Computed Column Mismatches panel (source vs recomputed, formula stated)
 *      e. Raw JSON viewer for debugging
 *   4. Unparsed rows panel (if any)
 *
 * Everything rendered here comes from the API response — no hardcoded values.
 */

export function renderProfile(result) {
  const profileSection = document.getElementById('profile-section');
  profileSection.classList.add('visible');
  // Target the .container inside the section for content injection
  let section = profileSection.querySelector('.container');
  if (!section) {
    section = document.createElement('div');
    section.className = 'container';
    profileSection.appendChild(section);
  }
  section.innerHTML = '';
  section.classList.add('fade-in');

  const { stage1, stage2, filename } = result;

  if (!stage2) {
    section.innerHTML = `<div class="status-banner visible error"><span>❌ Stage 2 profiling data is missing from the response.</span></div>`;
    return;
  }

  // --- Section title ---
  section.appendChild(el('div', { className: 'section-title' }, [
    '🧠 Data Profile Report',
  ]));
  section.appendChild(el('p', { className: 'section-subtitle' },
    [`Analysis of "${filename}" — ${stage2.total_tables} table(s) detected`]
  ));

  // --- Human summary card ---
  const summaryCard = el('div', { className: 'summary-card' });
  summaryCard.innerHTML = `<pre class="summary-pre">${escHtml(stage2.human_summary)}</pre>`;
  section.appendChild(summaryCard);

  // --- KPI strip ---
  section.appendChild(buildKpiStrip(stage2));

  // --- Stage-level warnings ---
  if (stage2.warnings && stage2.warnings.length) {
    stage2.warnings.forEach(w => {
      const banner = el('div', { className: 'status-banner visible info' });
      banner.innerHTML = `<span>⚠ ${escHtml(w)}</span>`;
      section.appendChild(banner);
    });
  }

  // --- Per-table tabs ---
  if (stage2.table_profiles && stage2.table_profiles.length > 0) {
    const tabBar = el('div', { className: 'tab-bar' });
    const tabPanels = el('div', {});

    stage2.table_profiles.forEach((tp, i) => {
      // Tab button
      const label = tp.source_sheet
        ? `Sheet: ${tp.source_sheet}`
        : tp.source_page
          ? `Page ${tp.source_page} / Table ${tp.table_index + 1}`
          : `Table ${tp.table_index + 1}`;

      const tabBtn = el('button', {
        className: `tab-btn ${i === 0 ? 'active' : ''}`,
        id: `tab-btn-${i}`,
        type: 'button',
        onclick: () => activateTab(i, stage2.table_profiles.length),
      }, [label]);
      tabBar.appendChild(tabBtn);

      // Tab panel
      const panel = el('div', {
        className: `tab-panel ${i === 0 ? 'active' : ''}`,
        id: `tab-panel-${i}`,
      });

      panel.appendChild(buildTableProfile(tp, stage1, i));
      tabPanels.appendChild(panel);
    });

    section.appendChild(tabBar);
    section.appendChild(tabPanels);
  }

  // --- Unparsed rows panel ---
  const allUnparsed = [...(stage1.unparsed_rows || [])];
  if (allUnparsed.length > 0) {
    section.appendChild(buildUnparsedPanel(allUnparsed));
  }

  // --- Raw JSON ---
  section.appendChild(buildJsonPanel(result));
}


// ---------------------------------------------------------------------------
// Sub-builders
// ---------------------------------------------------------------------------

function buildKpiStrip(stage2) {
  const kpis = [
    { value: stage2.total_tables,       label: 'Tables Found' },
    { value: stage2.total_detail_rows,  label: 'Detail Rows' },
    { value: stage2.total_categories,   label: 'Categories' },
    { value: stage2.total_anomalies,    label: 'Anomalies' },
    { value: stage2.total_mismatches,   label: 'Total Mismatches' },
  ];

  const strip = el('div', { className: 'kpi-strip' });
  kpis.forEach(k => {
    const card = el('div', { className: 'kpi-card' });
    card.innerHTML = `
      <div class="kpi-value">${k.value}</div>
      <div class="kpi-label">${escHtml(k.label)}</div>
    `;
    strip.appendChild(card);
  });
  return strip;
}


function buildTableProfile(tp, stage1, tableIdx) {
  const wrap = el('div', {});

  // --- Grain + time structure summary ---
  const infoBar = el('div', { style: 'margin-bottom:20px; color: var(--text-secondary); font-size:0.88rem; line-height:1.6;' });
  infoBar.innerHTML = `
    <b style="color:var(--text-primary)">Grain:</b> ${escHtml(tp.grain_description)}<br>
    ${tp.time_structure
      ? `<b style="color:var(--text-primary)">Time structure:</b> ${tp.time_structure.period_type}, 
         ${tp.time_structure.start} → ${tp.time_structure.end} 
         (${tp.time_structure.count} periods)`
      : '<b style="color:var(--text-primary)">Time structure:</b> Not detected'}
  `;
  wrap.appendChild(infoBar);

  // --- Column profiles ---
  wrap.appendChild(el('h3', { style: 'margin-bottom:12px; font-size:0.95rem;' }, ['Column Profiles']));
  wrap.appendChild(buildColumnProfileTable(tp.column_profiles));

  // --- Anomalies (always visible) ---
  const anomalyHeader = el('h3', {
    style: 'margin: 24px 0 12px; font-size:0.95rem; display:flex; align-items:center; gap:8px;',
  });
  anomalyHeader.innerHTML = `🔍 Anomalies <span class="chip" style="background:rgba(239,68,68,0.15);color:#f87171;">${tp.anomalies.length}</span>`;
  wrap.appendChild(anomalyHeader);

  if (tp.anomalies.length === 0) {
    wrap.appendChild(el('p', { style: 'color:var(--success); font-size:0.88rem;' }, ['✅ No anomalies detected in this table.']));
  } else {
    tp.anomalies.forEach(a => wrap.appendChild(buildAnomalyItem(a)));
  }

  // --- Computed column mismatches ---
  if (tp.computed_column_mismatches && tp.computed_column_mismatches.length > 0) {
    const mHead = el('h3', {
      style: 'margin: 24px 0 12px; font-size:0.95rem; display:flex; align-items:center; gap:8px;',
    });
    mHead.innerHTML = `⚠️ Computed Column Mismatches <span class="chip" style="background:rgba(245,158,11,0.15);color:#fbbf24;">${tp.computed_column_mismatches.length}</span>`;
    wrap.appendChild(mHead);

    const note = el('p', { style: 'font-size:0.82rem; color:var(--text-muted); margin-bottom:12px;' });
    note.innerHTML = `Each row below shows the value from <b style="color:var(--warning)">the source file</b> vs. our <b style="color:var(--info)">independently recomputed</b> value. Both are labeled so you can see which is which.`;
    wrap.appendChild(note);

    tp.computed_column_mismatches.forEach(m => wrap.appendChild(buildMismatchItem(m)));
  }

  return wrap;
}


function buildColumnProfileTable(cols) {
  if (!cols || cols.length === 0) {
    return el('p', { style: 'color:var(--text-muted);' }, ['No column profiles available.']);
  }

  const wrap = el('div', { className: 'data-table-wrap' });
  const tbl = el('table', { className: 'data-table' });

  tbl.innerHTML = `
    <thead>
      <tr>
        <th>#</th>
        <th>Header</th>
        <th>Inferred Type</th>
        <th>Confidence</th>
        <th>Null / Unique</th>
        <th>Sample Values</th>
        <th>Computed Col?</th>
        <th>Evidence</th>
      </tr>
    </thead>
  `;

  const tbody = el('tbody', {});
  cols.forEach(cp => {
    const tr = el('tr', {});
    tr.innerHTML = `
      <td class="mono">${cp.col_index}</td>
      <td><b>${escHtml(cp.header)}</b>${cp.period_label ? `<br><small class="mono text-muted">${escHtml(cp.period_label)}</small>` : ''}</td>
      <td><span class="type-badge type-${cp.inferred_type}">${cp.inferred_type}</span></td>
      <td>
        <div class="conf-bar">
          <div class="conf-track"><div class="conf-fill" style="width:${Math.round(cp.type_confidence * 100)}%"></div></div>
          <span class="conf-pct">${Math.round(cp.type_confidence * 100)}%</span>
        </div>
      </td>
      <td class="mono">${cp.null_count} null / ${cp.unique_count} unique</td>
      <td style="font-size:0.78rem; color:var(--text-muted);">${(cp.sample_values||[]).map(v => escHtml(String(v))).join(', ') || '—'}</td>
      <td style="text-align:center;">${cp.is_computed_column ? '⚠️ Yes' : '—'}</td>
      <td style="font-size:0.78rem; color:var(--text-muted); max-width:260px; line-height:1.5;">${escHtml(cp.type_evidence || '')}</td>
    `;
    tbody.appendChild(tr);
  });

  tbl.appendChild(tbody);
  wrap.appendChild(tbl);
  return wrap;
}


function buildAnomalyItem(a) {
  const icons = {
    negative_in_positive_column: '🔴',
    blank_run:                   '🟡',
    ocr_corruption:              '🔵',
    duplicate_row:               '🟣',
  };
  const typeLabels = {
    negative_in_positive_column: 'Negative Value in Positive Column',
    blank_run:                   'Blank Run',
    ocr_corruption:              'Possible OCR Corruption',
    duplicate_row:               'Duplicate Row',
  };
  const typeClasses = {
    negative_in_positive_column: 'negative',
    blank_run:                   'blank',
    ocr_corruption:              'ocr',
    duplicate_row:               'duplicate',
  };

  const item = el('div', { className: 'anomaly-item' });
  item.innerHTML = `
    <span class="anomaly-icon">${icons[a.anomaly_type] || '⚠️'}</span>
    <div class="anomaly-body">
      <div class="anomaly-type ${typeClasses[a.anomaly_type] || ''}">${typeLabels[a.anomaly_type] || a.anomaly_type}</div>
      <div class="anomaly-desc">${escHtml(a.description)}</div>
    </div>
  `;
  return item;
}


function buildMismatchItem(m) {
  const item = el('div', { className: 'mismatch-item' });
  const delta = m.delta || 0;
  const deltaClass = delta < 0 ? 'neg' : 'pos';
  const sign = delta >= 0 ? '+' : '';

  item.innerHTML = `
    <div style="font-weight:600; margin-bottom:8px; color:var(--text-primary);">
      Row: "${escHtml(m.row_description)}" — Column: "${escHtml(m.column_header)}"
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
        <span class="mismatch-val-label">Delta (source − recomputed)</span>
        <span class="mismatch-val-num delta ${deltaClass}">${sign}${fmt(delta)}</span>
      </div>
    </div>
    <div class="mismatch-formula">Recomputed from: ${escHtml(m.recomputed_from)}</div>
    ${m.source_page ? `<div class="mismatch-formula">Source: page ${m.source_page}, line ${m.source_line}</div>` : ''}
  `;
  return item;
}


function buildUnparsedPanel(rows) {
  const wrap = el('div', {});
  const head = el('h3', { style: 'margin: 24px 0 12px; font-size:0.95rem;' });
  head.innerHTML = `⛔ Unparsed Rows <span class="chip" style="background:rgba(239,68,68,0.1);color:#f87171;">${rows.length}</span>`;
  wrap.appendChild(head);

  const note = el('p', { style: 'font-size:0.82rem; color:var(--text-muted); margin-bottom:12px;' },
    ['These rows could not be parsed. They are never silently dropped — review them here.']);
  wrap.appendChild(note);

  rows.forEach(r => {
    const item = el('div', { className: 'unparsed-item' });
    item.innerHTML = `
      <div class="unparsed-source">Source: ${escHtml(r.source || '?')} — Reason: ${escHtml(r.reason || '?')}</div>
      <div class="unparsed-text">${escHtml((r.raw_text || '').substring(0, 400))}</div>
    `;
    wrap.appendChild(item);
  });

  return wrap;
}


function buildJsonPanel(result) {
  const details = document.createElement('details');
  details.style.marginTop = '32px';

  const summary = el('summary', {
    style: 'cursor:pointer; color:var(--text-muted); font-size:0.85rem; margin-bottom:12px; user-select:none;',
  }, ['🔧 Raw Pipeline JSON (debugging)']);
  details.appendChild(summary);

  const pre = el('div', { className: 'json-viewer' });
  pre.textContent = JSON.stringify(result, null, 2);
  details.appendChild(pre);

  return details;
}


// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function activateTab(activeIdx, total) {
  for (let i = 0; i < total; i++) {
    document.getElementById(`tab-btn-${i}`)?.classList.toggle('active', i === activeIdx);
    document.getElementById(`tab-panel-${i}`)?.classList.toggle('active', i === activeIdx);
  }
}

function el(tag, attrs = {}, children = []) {
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

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function fmt(n) {
  if (n === null || n === undefined) return '—';
  return Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
