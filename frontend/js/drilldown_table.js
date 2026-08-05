/**
 * drilldown_table.js — Sortable, filterable, paginated drilldown table
 *
 * Renders a collapsible table card for a raw table from the PipelineResult.
 * Supports:
 *   - Search/filter across all text columns
 *   - Click-to-sort on any column header
 *   - Row-role colour coding (detail / subtotal / grand_total / section_header)
 *   - Anomaly & mismatch cell highlighting
 *   - Pagination (30 rows/page)
 *
 * Exports:
 *   buildDrilldownTable(tableIndex, pipelineResult, opts?) → HTMLElement
 */

const PAGE_SIZE = 30;

/**
 * Build a collapsible drilldown table card.
 * @param {number} tableIndex
 * @param {object} pipelineResult  - full PipelineResult from API
 * @param {object} [opts]
 * @param {boolean} [opts.startOpen=false]
 * @returns {HTMLElement}
 */
export function buildDrilldownTable(tableIndex, pipelineResult, opts = {}) {
  const { startOpen = false } = opts;
  const rawTable = pipelineResult.stage1?.tables?.[tableIndex];
  const tp = pipelineResult.stage2?.table_profiles?.[tableIndex];
  if (!rawTable) return _emptyCard(tableIndex);

  const headers = rawTable.headers;
  const rows = rawTable.rows;
  const roles = (tp?.row_roles) || rows.map(() => 'detail');

  // Build flagged cells lookup: { "rowIdx_colIdx": "anomaly"|"mismatch" }
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
  let sortCol = -1;
  let sortDir = 1;
  let filterText = '';
  let currentPage = 0;
  let isOpen = startOpen;

  // ── Card wrapper ──────────────────────────────────────────────────────────
  const card = document.createElement('div');
  card.className = 'drilldown-card';

  // ── Header ───────────────────────────────────────────────────────────────
  const sheetLabel = rawTable.source_sheet ? ` — ${rawTable.source_sheet}` : '';
  const pageLabel  = rawTable.source_page  ? ` — Page ${rawTable.source_page}`  : '';
  const title = `Table ${tableIndex + 1}${sheetLabel}${pageLabel}`;

  const header = document.createElement('div');
  header.className = 'drilldown-header';
  header.setAttribute('role', 'button');
  header.setAttribute('aria-expanded', String(isOpen));
  header.setAttribute('tabindex', '0');
  header.innerHTML = `
    <div class="drilldown-title">
      <span>📋</span> ${escHtml(title)}
      <span class="chip" style="background:rgba(124,58,237,0.12);color:#a78bfa;">
        ${rows.length} rows × ${headers.length} cols
      </span>
    </div>
    <span class="drilldown-toggle-icon ${isOpen ? 'open' : ''}">▼</span>
  `;
  card.appendChild(header);

  // ── Controls ──────────────────────────────────────────────────────────────
  const controls = document.createElement('div');
  controls.className = 'drilldown-controls';
  controls.innerHTML = `
    <input class="drilldown-search" type="search" placeholder="Search all columns…"
           id="dt-search-${tableIndex}" aria-label="Search table" />
    <span class="drilldown-sort-label">Click column headers to sort</span>
  `;
  card.appendChild(controls);

  // ── Body ─────────────────────────────────────────────────────────────────
  const body = document.createElement('div');
  body.className = `drilldown-body ${isOpen ? 'open' : ''}`;

  const tableWrap = document.createElement('div');
  tableWrap.className = 'drilldown-table-wrap';

  const tbl = document.createElement('table');
  tbl.className = 'drilldown-table';
  tbl.setAttribute('role', 'grid');

  // Table head
  const thead = document.createElement('thead');
  const headRow = document.createElement('tr');
  headers.forEach((h, ci) => {
    const th = document.createElement('th');
    th.setAttribute('scope', 'col');
    th.innerHTML = `${escHtml(h)} <span class="sort-arrow">⇅</span>`;
    th.addEventListener('click', () => {
      if (sortCol === ci) sortDir *= -1;
      else { sortCol = ci; sortDir = 1; }
      currentPage = 0;
      // Update header classes
      headRow.querySelectorAll('th').forEach((t, i) => t.classList.toggle('sorted', i === ci));
      headRow.querySelectorAll('.sort-arrow').forEach((a, i) => {
        a.textContent = i === ci ? (sortDir === 1 ? '↑' : '↓') : '⇅';
      });
      renderBody();
    });
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  tbl.appendChild(thead);

  const tbody = document.createElement('tbody');
  tbl.appendChild(tbody);
  tableWrap.appendChild(tbl);

  const pagination = document.createElement('div');
  pagination.className = 'drilldown-pagination';

  body.appendChild(tableWrap);
  body.appendChild(pagination);
  card.appendChild(body);

  // ── Render function ───────────────────────────────────────────────────────
  function getFilteredSorted() {
    const lower = filterText.toLowerCase();
    let data = rows.map((r, i) => ({ row: r, role: roles[i] }));

    // Filter
    if (lower) {
      data = data.filter(({ row }) =>
        row.cells.some(c => String(c.value ?? '').toLowerCase().includes(lower))
      );
    }

    // Sort
    if (sortCol >= 0) {
      data.sort((a, b) => {
        const av = a.row.cells[sortCol]?.value ?? '';
        const bv = b.row.cells[sortCol]?.value ?? '';
        if (typeof av === 'number' && typeof bv === 'number') return sortDir * (av - bv);
        return sortDir * String(av).localeCompare(String(bv));
      });
    }

    return data;
  }

  function renderBody() {
    const data = getFilteredSorted();
    const totalPages = Math.max(1, Math.ceil(data.length / PAGE_SIZE));
    currentPage = Math.min(currentPage, totalPages - 1);

    const slice = data.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);

    tbody.innerHTML = '';

    if (slice.length === 0) {
      const td = document.createElement('td');
      td.colSpan = headers.length;
      td.className = 'drilldown-empty';
      td.textContent = 'No rows match your search.';
      const tr = document.createElement('tr');
      tr.appendChild(td);
      tbody.appendChild(tr);
    } else {
      for (const { row, role } of slice) {
        const tr = document.createElement('tr');
        const roleClass = {
          subtotal: 'row-subtotal',
          grand_total: 'row-grand-total',
          section_header: 'row-section-header',
        }[role] || '';
        if (roleClass) tr.className = roleClass;

        for (let ci = 0; ci < headers.length; ci++) {
          const cell = row.cells[ci];
          const td = document.createElement('td');
          const val = cell ? cell.value : null;
          td.textContent = val !== null && val !== undefined ? String(val) : '';
          td.title = td.textContent;

          const flag = flagged[`${row.row_index}_${ci}`];
          if (flag === 'anomaly') td.classList.add('cell-anomaly');
          else if (flag === 'mismatch') td.classList.add('cell-mismatch');

          tr.appendChild(td);
        }
        tbody.appendChild(tr);
      }
    }

    // Pagination controls
    pagination.innerHTML = `
      <span>${data.length} row(s) — Page ${currentPage + 1} of ${totalPages}</span>
      <div style="display:flex;gap:6px;">
        <button id="dt-prev-${tableIndex}" ${currentPage === 0 ? 'disabled' : ''}>‹ Prev</button>
        <button id="dt-next-${tableIndex}" ${currentPage >= totalPages - 1 ? 'disabled' : ''}>Next ›</button>
      </div>
    `;
    pagination.querySelector(`#dt-prev-${tableIndex}`)?.addEventListener('click', () => {
      if (currentPage > 0) { currentPage--; renderBody(); }
    });
    pagination.querySelector(`#dt-next-${tableIndex}`)?.addEventListener('click', () => {
      if (currentPage < totalPages - 1) { currentPage++; renderBody(); }
    });
  }

  // ── Toggle behaviour ──────────────────────────────────────────────────────
  function toggleOpen() {
    isOpen = !isOpen;
    body.classList.toggle('open', isOpen);
    header.setAttribute('aria-expanded', String(isOpen));
    header.querySelector('.drilldown-toggle-icon').classList.toggle('open', isOpen);
    if (isOpen) renderBody();
  }

  header.addEventListener('click', toggleOpen);
  header.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleOpen(); }
  });

  // Search
  controls.querySelector(`#dt-search-${tableIndex}`).addEventListener('input', e => {
    filterText = e.target.value;
    currentPage = 0;
    if (isOpen) renderBody();
  });

  // Initial render if open
  if (isOpen) renderBody();

  return card;
}


function _emptyCard(tableIndex) {
  const card = document.createElement('div');
  card.className = 'drilldown-card';
  card.innerHTML = `<div class="drilldown-header"><div class="drilldown-title">Table ${tableIndex + 1} — No data</div></div>`;
  return card;
}

function escHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
