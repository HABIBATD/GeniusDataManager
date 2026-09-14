/**
 * drilldown_table.js — Intelligent Interactive Data Grid & Composer
 *
 * Features:
 *   - Dynamic Column Composer (show/hide columns via interactive menu)
 *   - Live In-Browser Group By & Aggregations (Sum, Avg, Count, Min, Max)
 *   - Real-time search across all visible columns
 *   - Click-to-sort on any column
 *   - Row role styling (detail, subtotal, grand_total, section_header)
 *   - Anomaly and mismatch highlighting
 *   - Clean pagination
 */

const PAGE_SIZE = 25;

export function buildDrilldownTable(tableIndex, pipelineResult, opts = {}) {
  const { startOpen = true, isComposedView = false } = opts;
  let rawTable;
  let tp;

  if (isComposedView) {
    rawTable = _buildMasterComposedTable(pipelineResult);
    tp = null;
  } else {
    rawTable = pipelineResult.stage1?.tables?.[tableIndex];
    tp = pipelineResult.stage2?.table_profiles?.[tableIndex];
  }

  if (!rawTable) return _emptyCard(tableIndex);

  const allHeaders = [...rawTable.headers];
  const allRows = rawTable.rows;
  const roles = tp?.row_roles || allRows.map(() => 'detail');

  // Flagged cells lookup: { "rowIdx_colIdx": "anomaly"|"mismatch" }
  const flagged = {};
  if (tp) {
    for (const a of (tp.anomalies || [])) {
      if (a.row_index != null && a.col_index != null)
        flagged[`${a.row_index}_${a.col_index}`] = 'anomaly';
    }
    for (const m of (tp.computed_column_mismatches || [])) {
      const mCol = (tp.column_profiles || []).findIndex(cp => cp.header === m.column_header);
      if (mCol >= 0)
        flagged[`${m.row_index}_${mCol}`] = 'mismatch';
    }
  }

  // Reactive state
  let visibleHeaders = new Set(allHeaders);
  let sortCol = -1;
  let sortDir = 1;
  let filterText = '';
  let currentPage = 0;
  let isOpen = startOpen;
  let groupByCol = '';
  let aggregateCol = '';
  let aggregateFunc = 'sum'; // sum, avg, count, min, max

  // ── Card wrapper ──
  const card = document.createElement('div');
  card.className = 'drilldown-card';

  // ── Header ──
  const sheetLabel = rawTable.source_sheet ? ` — ${rawTable.source_sheet}` : '';
  const title = isComposedView ? `🌟 Consolidated Master View (All Tables Composed)` : `Table ${tableIndex + 1}${sheetLabel}`;

  const header = document.createElement('div');
  header.className = 'drilldown-header';
  header.setAttribute('role', 'button');
  header.setAttribute('aria-expanded', String(isOpen));
  header.setAttribute('tabindex', '0');
  header.innerHTML = `
    <div class="drilldown-title">
      <span>${isComposedView ? '🌟' : '📋'}</span> ${escHtml(title)}
      <span class="chip" style="background:rgba(99,102,241,0.15);color:#818cf8;">
        ${allRows.length} rows × ${allHeaders.length} cols
      </span>
    </div>
    <span class="drilldown-toggle-icon ${isOpen ? 'open' : ''}">▼</span>
  `;
  card.appendChild(header);

  // ── Composer Toolbar (Search + Column Toggle + Group By) ──
  const controls = document.createElement('div');
  controls.className = 'drilldown-controls-bar';

  // Search input
  const searchWrap = document.createElement('div');
  searchWrap.className = 'composer-search-wrap';
  searchWrap.innerHTML = `
    <input class="drilldown-search" type="search" placeholder="Search rows & columns…"
           id="dt-search-${tableIndex}" aria-label="Search table" />
  `;

  // Column visibility button & popover
  const colToggleWrap = document.createElement('div');
  colToggleWrap.className = 'composer-col-wrap';
  colToggleWrap.innerHTML = `
    <button type="button" class="btn-composer-tool" id="col-btn-${tableIndex}">
      <span>👁️ Columns (${visibleHeaders.size}/${allHeaders.length})</span> ▾
    </button>
    <div class="col-picker-dropdown hidden" id="col-dropdown-${tableIndex}"></div>
  `;

  // Group By & Aggregation Bar
  const groupWrap = document.createElement('div');
  groupWrap.className = 'composer-group-wrap';

  // Detect numeric columns for aggregation
  const numericHeaders = allHeaders.filter((h, ci) => {
    return allRows.some(r => typeof r.cells[ci]?.value === 'number');
  });

  groupWrap.innerHTML = `
    <div class="composer-group-row">
      <label class="composer-label">Group By:</label>
      <select class="composer-select" id="group-by-${tableIndex}">
        <option value="">(None - Raw Rows)</option>
        ${allHeaders.map(h => `<option value="${escHtml(h)}">${escHtml(h)}</option>`).join('')}
      </select>

      <label class="composer-label">Agg:</label>
      <select class="composer-select" id="agg-func-${tableIndex}">
        <option value="sum">Sum</option>
        <option value="avg">Average</option>
        <option value="count">Count</option>
        <option value="min">Min</option>
        <option value="max">Max</option>
      </select>

      <label class="composer-label">Metric:</label>
      <select class="composer-select" id="agg-metric-${tableIndex}">
        ${numericHeaders.map(h => `<option value="${escHtml(h)}">${escHtml(h)}</option>`).join('')}
      </select>
    </div>
  `;

  controls.appendChild(searchWrap);
  controls.appendChild(colToggleWrap);
  controls.appendChild(groupWrap);
  card.appendChild(controls);

  // ── Body ──
  const body = document.createElement('div');
  body.className = `drilldown-body ${isOpen ? 'open' : ''}`;

  const tableWrap = document.createElement('div');
  tableWrap.className = 'drilldown-table-wrap';

  const tbl = document.createElement('table');
  tbl.className = 'drilldown-table';
  tbl.setAttribute('role', 'grid');

  const thead = document.createElement('thead');
  const tbody = document.createElement('tbody');
  tbl.appendChild(thead);
  tbl.appendChild(tbody);
  tableWrap.appendChild(tbl);
  body.appendChild(tableWrap);

  // Pagination Footer
  const footer = document.createElement('div');
  footer.className = 'drilldown-footer';
  body.appendChild(footer);
  card.appendChild(body);

  // ── Populate Column Dropdown ──
  const dropdown = colToggleWrap.querySelector(`#col-dropdown-${tableIndex}`);
  const colBtn = colToggleWrap.querySelector(`#col-btn-${tableIndex}`);

  function buildColumnPicker() {
    dropdown.innerHTML = `
      <div class="col-picker-actions">
        <button type="button" class="btn-text" id="select-all-${tableIndex}">Select All</button>
        <button type="button" class="btn-text" id="select-none-${tableIndex}">Reset</button>
      </div>
    `;
    allHeaders.forEach(h => {
      const label = document.createElement('label');
      label.className = 'col-checkbox-label';
      const isChecked = visibleHeaders.has(h);
      label.innerHTML = `
        <input type="checkbox" ${isChecked ? 'checked' : ''} value="${escHtml(h)}">
        <span>${escHtml(h)}</span>
      `;
      const cb = label.querySelector('input');
      cb.addEventListener('change', () => {
        if (cb.checked) visibleHeaders.add(h);
        else {
          if (visibleHeaders.size > 1) visibleHeaders.delete(h);
          else cb.checked = true; // keep at least 1
        }
        colBtn.querySelector('span').textContent = `👁️ Columns (${visibleHeaders.size}/${allHeaders.length})`;
        renderTable();
      });
      dropdown.appendChild(label);
    });

    dropdown.querySelector(`#select-all-${tableIndex}`)?.addEventListener('click', () => {
      allHeaders.forEach(h => visibleHeaders.add(h));
      dropdown.querySelectorAll('input[type="checkbox"]').forEach(c => c.checked = true);
      colBtn.querySelector('span').textContent = `👁️ Columns (${visibleHeaders.size}/${allHeaders.length})`;
      renderTable();
    });

    dropdown.querySelector(`#select-none-${tableIndex}`)?.addEventListener('click', () => {
      visibleHeaders = new Set([allHeaders[0]]);
      dropdown.querySelectorAll('input[type="checkbox"]').forEach((c, idx) => c.checked = (idx === 0));
      colBtn.querySelector('span').textContent = `👁️ Columns (${visibleHeaders.size}/${allHeaders.length})`;
      renderTable();
    });
  }
  buildColumnPicker();

  colBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    dropdown.classList.toggle('hidden');
  });

  document.addEventListener('click', (e) => {
    if (!colToggleWrap.contains(e.target)) {
      dropdown.classList.add('hidden');
    }
  });

  // ── Header toggle ──
  header.addEventListener('click', () => {
    isOpen = !isOpen;
    header.setAttribute('aria-expanded', String(isOpen));
    body.classList.toggle('open', isOpen);
    header.querySelector('.drilldown-toggle-icon').classList.toggle('open', isOpen);
  });

  // ── Search & Group By Events ──
  const searchInput = controls.querySelector(`#dt-search-${tableIndex}`);
  searchInput.addEventListener('input', e => {
    filterText = e.target.value.trim().toLowerCase();
    currentPage = 0;
    renderTable();
  });

  const groupSelect = controls.querySelector(`#group-by-${tableIndex}`);
  const aggFuncSelect = controls.querySelector(`#agg-func-${tableIndex}`);
  const aggMetricSelect = controls.querySelector(`#agg-metric-${tableIndex}`);

  groupSelect.addEventListener('change', () => {
    groupByCol = groupSelect.value;
    currentPage = 0;
    renderTable();
  });
  aggFuncSelect.addEventListener('change', () => {
    aggregateFunc = aggFuncSelect.value;
    renderTable();
  });
  aggMetricSelect.addEventListener('change', () => {
    aggregateCol = aggMetricSelect.value;
    renderTable();
  });

  // ── Render Function ──
  function renderTable() {
    // If grouping is active, compose grouped rows
    if (groupByCol) {
      renderGroupedView();
      return;
    }

    const activeHeaders = allHeaders.filter(h => visibleHeaders.has(h));
    const activeIndices = activeHeaders.map(h => allHeaders.indexOf(h));

    // Filter rows
    let rowsToDisplay = allRows.map((r, i) => ({ row: r, origIdx: i, role: roles[i] }));
    if (filterText) {
      rowsToDisplay = rowsToDisplay.filter(({ row }) => {
        return row.cells.some(c => String(c.value ?? '').toLowerCase().includes(filterText));
      });
    }

    // Sort rows
    if (sortCol >= 0 && sortCol < allHeaders.length) {
      rowsToDisplay.sort((a, b) => {
        const valA = a.row.cells[sortCol]?.value ?? '';
        const valB = b.row.cells[sortCol]?.value ?? '';
        if (typeof valA === 'number' && typeof valB === 'number') {
          return (valA - valB) * sortDir;
        }
        return String(valA).localeCompare(String(valB)) * sortDir;
      });
    }

    // Build thead
    thead.innerHTML = '';
    const hr = document.createElement('tr');
    activeHeaders.forEach(h => {
      const origCi = allHeaders.indexOf(h);
      const th = document.createElement('th');
      th.setAttribute('scope', 'col');
      const arrow = sortCol === origCi ? (sortDir === 1 ? '▲' : '▼') : '⇅';
      th.innerHTML = `<span>${escHtml(h)}</span> <span class="sort-arrow">${arrow}</span>`;
      th.addEventListener('click', () => {
        if (sortCol === origCi) sortDir = -sortDir;
        else { sortCol = origCi; sortDir = 1; }
        renderTable();
      });
      hr.appendChild(th);
    });
    thead.appendChild(hr);

    // Pagination slice
    const totalCount = rowsToDisplay.length;
    const totalPages = Math.ceil(totalCount / PAGE_SIZE) || 1;
    if (currentPage >= totalPages) currentPage = totalPages - 1;
    if (currentPage < 0) currentPage = 0;

    const pageRows = rowsToDisplay.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);

    // Build tbody
    tbody.innerHTML = '';
    if (!pageRows.length) {
      tbody.innerHTML = `<tr><td colspan="${activeHeaders.length}" style="text-align:center;color:var(--text-muted);padding:24px;">No rows matching filter.</td></tr>`;
    } else {
      pageRows.forEach(({ row, origIdx, role }) => {
        const tr = document.createElement('tr');
        tr.className = `role-${role}`;
        activeIndices.forEach(ci => {
          const td = document.createElement('td');
          const cell = row.cells[ci];
          const val = cell?.value;
          const display = val === null || val === undefined ? '—' : (typeof val === 'number' ? val.toLocaleString() : String(val));
          td.textContent = display;

          const flag = flagged[`${origIdx}_${ci}`];
          if (flag) td.classList.add(`cell-${flag}`);
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
    }

    // Update footer
    footer.innerHTML = `
      <span class="drilldown-page-info">
        Showing <b>${pageRows.length}</b> of <b>${totalCount}</b> rows
        ${filterText ? `(filtered from ${allRows.length})` : ''}
      </span>
      <div class="drilldown-page-btns">
        <button type="button" class="btn-page" id="btn-prev" ${currentPage === 0 ? 'disabled' : ''}>‹ Prev</button>
        <span class="page-num">Page ${currentPage + 1} of ${totalPages}</span>
        <button type="button" class="btn-page" id="btn-next" ${currentPage >= totalPages - 1 ? 'disabled' : ''}>Next ›</button>
      </div>
    `;

    footer.querySelector('#btn-prev')?.addEventListener('click', () => {
      if (currentPage > 0) { currentPage--; renderTable(); }
    });
    footer.querySelector('#btn-next')?.addEventListener('click', () => {
      if (currentPage < totalPages - 1) { currentPage++; renderTable(); }
    });
  }

  // ── Grouped View Logic ──
  function renderGroupedView() {
    const groupColIdx = allHeaders.indexOf(groupByCol);
    const metricCol = aggregateCol || numericHeaders[0] || allHeaders[1];
    const metricColIdx = allHeaders.indexOf(metricCol);

    const groups = {};
    allRows.forEach(r => {
      const gKey = String(r.cells[groupColIdx]?.value ?? '—');
      if (!groups[gKey]) groups[gKey] = [];
      const v = r.cells[metricColIdx]?.value;
      const num = typeof v === 'number' ? v : parseFloat(v);
      if (!isNaN(num)) groups[gKey].push(num);
    });

    const groupedData = Object.entries(groups).map(([key, vals]) => {
      let aggVal = 0;
      if (vals.length > 0) {
        if (aggregateFunc === 'sum') aggVal = vals.reduce((a, b) => a + b, 0);
        else if (aggregateFunc === 'avg') aggVal = vals.reduce((a, b) => a + b, 0) / vals.length;
        else if (aggregateFunc === 'count') aggVal = vals.length;
        else if (aggregateFunc === 'min') aggVal = Math.min(...vals);
        else if (aggregateFunc === 'max') aggVal = Math.max(...vals);
      }
      return { group: key, count: vals.length, aggregate: aggVal };
    });

    // Render grouped table
    thead.innerHTML = `
      <tr>
        <th scope="col">${escHtml(groupByCol)} (Group)</th>
        <th scope="col">Record Count</th>
        <th scope="col">${escHtml(aggregateFunc.toUpperCase())} of ${escHtml(metricCol)}</th>
      </tr>
    `;

    tbody.innerHTML = '';
    groupedData.forEach(item => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td style="font-weight:600;">${escHtml(item.group)}</td>
        <td>${item.count.toLocaleString()}</td>
        <td style="color:var(--accent-1);font-weight:600;">${typeof item.aggregate === 'number' ? item.aggregate.toLocaleString(undefined, { maximumFractionDigits: 2 }) : item.aggregate}</td>
      `;
      tbody.appendChild(tr);
    });

    footer.innerHTML = `
      <span class="drilldown-page-info">
        Composed <b>${groupedData.length}</b> aggregate groups from <b>${allRows.length}</b> source rows.
      </span>
    `;
  }

  renderTable();
  return card;
}


function _buildMasterComposedTable(pipelineResult) {
  const tables = pipelineResult.stage1?.tables || [];
  if (!tables.length) return null;

  // Union all headers preserving order
  const unionHeaders = [];
  const seen = new Set();
  tables.forEach(t => {
    t.headers.forEach(h => {
      if (!seen.has(h)) {
        seen.add(h);
        unionHeaders.push(h);
      }
    });
  });

  // Combine rows with source table indicator
  const fullHeaders = ['_source_table', ...unionHeaders];
  const combinedRows = [];

  tables.forEach(t => {
    const tableName = t.source_sheet || `Table ${t.table_index + 1}`;
    t.rows.forEach(r => {
      const cells = [
        { col_index: 0, value: tableName, raw_text: tableName },
      ];
      unionHeaders.forEach((uh, ci) => {
        const origCi = t.headers.indexOf(uh);
        const val = origCi >= 0 ? r.cells[origCi]?.value : null;
        cells.push({
          col_index: ci + 1,
          value: val,
          raw_text: val === null || val === undefined ? '' : String(val),
        });
      });
      combinedRows.push({
        row_index: combinedRows.length,
        source_line: r.source_line,
        cells,
      });
    });
  });

  return {
    headers: fullHeaders,
    rows: combinedRows,
    source_sheet: "Master Composed Dataset",
  };
}


function _emptyCard(idx) {
  const c = document.createElement('div');
  c.className = 'drilldown-card';
  c.innerHTML = `<div class="drilldown-header"><span style="color:var(--text-muted)">Table ${idx + 1} — No data available</span></div>`;
  return c;
}

function escHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
