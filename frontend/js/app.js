/**
 * GeniusDataManager — Main Wizard Application State Controller
 */

import * as api from './api.js';
import * as ui from './ui_components.js';

// Global wizard state
const state = {
  currentStep: 1,
  fileId: null,
  filename: null,
  sheetNames: null,
  currentSheet: null,
  schema: null,
  alignedResult: null,
  analysisResult: null,
  selectedAnalysisType: 'sales_analysis',
};

document.addEventListener('DOMContentLoaded', () => {
  initEventListeners();
});

function initEventListeners() {
  // Stepper clicks
  document.querySelectorAll('.step-item').forEach(item => {
    item.addEventListener('click', () => {
      const targetStep = parseInt(item.dataset.step, 10);
      if (targetStep < state.currentStep || canNavigateTo(targetStep)) {
        goToStep(targetStep);
      }
    });
  });

  // Drag & drop upload
  const dropZone = document.getElementById('upload-zone');
  const fileInput = document.getElementById('file-input');

  if (dropZone && fileInput) {
    dropZone.addEventListener('click', () => fileInput.click());
    dropZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropZone.classList.add('drag-over');
    });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
    dropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropZone.classList.remove('drag-over');
      if (e.dataTransfer.files.length > 0) {
        handleFileUpload(e.dataTransfer.files[0]);
      }
    });

    fileInput.addEventListener('change', (e) => {
      if (e.target.files.length > 0) {
        handleFileUpload(e.target.files[0]);
      }
    });
  }

  // Demo presets
  document.getElementById('btn-preset-sales')?.addEventListener('click', () => loadPreset('sample_sales.csv'));
  document.getElementById('btn-preset-excel')?.addEventListener('click', () => loadPreset('sample_quarterly.xlsx'));
  document.getElementById('btn-preset-json')?.addEventListener('click', () => loadPreset('sample_customers.json'));

  // Sheet selector change
  document.getElementById('sheet-select')?.addEventListener('change', (e) => {
    state.currentSheet = e.target.value;
    fetchAndDisplaySchema();
  });

  // Step 2 -> Step 3
  document.getElementById('btn-step2-next')?.addEventListener('click', () => goToStep(3));

  // Step 3: Filter rule button
  document.getElementById('btn-add-filter')?.addEventListener('click', () => {
    if (state.schema && state.schema.columns) {
      ui.renderFilterRow(state.schema.columns);
    }
  });

  // Step 3 -> Step 4 (Run Alignment)
  document.getElementById('btn-step3-next')?.addEventListener('click', handleAlignmentSubmit);

  // Step 4: Analysis card selection
  document.querySelectorAll('.analysis-card').forEach(card => {
    card.addEventListener('click', () => {
      document.querySelectorAll('.analysis-card').forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      state.selectedAnalysisType = card.dataset.analysis;
      updateAnalysisOptionsUI();
    });
  });

  // Step 4 -> Step 5 (Run Analysis)
  document.getElementById('btn-run-analysis')?.addEventListener('click', handleAnalysisSubmit);

  // Step 5: Export buttons
  document.getElementById('btn-export-csv')?.addEventListener('click', () => triggerExport('csv'));
  document.getElementById('btn-export-xlsx')?.addEventListener('click', () => triggerExport('xlsx'));
  document.getElementById('btn-export-json')?.addEventListener('click', () => triggerExport('json'));

  // Step 5: Restart button
  document.getElementById('btn-start-over')?.addEventListener('click', () => resetWizard());
}

function canNavigateTo(step) {
  if (step === 2 && state.fileId) return true;
  if (step === 3 && state.schema) return true;
  if (step === 4 && state.alignedResult) return true;
  if (step === 5 && state.analysisResult) return true;
  return false;
}

function goToStep(stepNumber) {
  state.currentStep = stepNumber;

  // Update Stepper UI
  document.querySelectorAll('.step-item').forEach(item => {
    const s = parseInt(item.dataset.step, 10);
    item.classList.remove('active', 'completed');
    if (s === stepNumber) {
      item.classList.add('active');
    } else if (s < stepNumber) {
      item.classList.add('completed');
    }
  });

  // Toggle step sections
  document.querySelectorAll('.wizard-step-section').forEach(sec => {
    sec.classList.add('hidden');
  });

  const activeSection = document.getElementById(`step-${stepNumber}-section`);
  if (activeSection) {
    activeSection.classList.remove('hidden');
  }

  // Step-specific initialization
  if (stepNumber === 3) {
    populateTargetColumnSelectors();
  }
}

async function handleFileUpload(file) {
  showStatusBanner('Uploading and detecting structure…', 'info');
  try {
    const uploadRes = await api.uploadFile(file);
    state.fileId = uploadRes.file_id;
    state.filename = uploadRes.filename;
    state.sheetNames = uploadRes.sheet_names;
    state.currentSheet = uploadRes.default_sheet;

    // Show sheet selector if Excel with multiple sheets
    const sheetCard = document.getElementById('sheet-selector-card');
    const sheetSelect = document.getElementById('sheet-select');
    if (state.sheetNames && state.sheetNames.length > 1) {
      sheetSelect.innerHTML = state.sheetNames.map(s => `<option value="${s}">${s}</option>`).join('');
      sheetCard.classList.remove('hidden');
    } else {
      sheetCard.classList.add('hidden');
    }

    showStatusBanner(`Successfully loaded '${file.name}'!`, 'success');
    await fetchAndDisplaySchema();
    goToStep(2);
  } catch (err) {
    showStatusBanner(err.message, 'error');
  }
}

async function loadPreset(filename) {
  showStatusBanner(`Loading demo fixture '${filename}'…`, 'info');
  try {
    const response = await fetch(`/fixtures/${filename}`);
    if (!response.ok) {
      throw new Error(`Preset fixture '${filename}' not found.`);
    }
    const blob = await response.blob();
    const file = new File([blob], filename, { type: blob.type || 'text/csv' });
    await handleFileUpload(file);
  } catch (err) {
    showStatusBanner(`Preset load error: ${err.message}`, 'error');
  }
}

async function fetchAndDisplaySchema() {
  try {
    const schemaRes = await api.getSchema(state.fileId, state.currentSheet);
    state.schema = schemaRes;

    document.getElementById('meta-file-name').textContent = schemaRes.filename + (schemaRes.sheet_name ? ` (${schemaRes.sheet_name})` : '');
    document.getElementById('meta-row-count').textContent = schemaRes.row_count.toLocaleString();
    document.getElementById('meta-col-count').textContent = schemaRes.column_count;

    ui.renderSchemaTable(schemaRes.columns, schemaRes.preview);
    ui.renderMappingRows(schemaRes.columns);

    // Reset filter rules list
    const filterContainer = document.getElementById('filter-rules-list');
    if (filterContainer) filterContainer.innerHTML = '';
  } catch (err) {
    showStatusBanner(err.message, 'error');
  }
}

function populateTargetColumnSelectors() {
  if (!state.schema) return;
  const cols = state.schema.columns;

  const targetSelect = document.getElementById('analysis-target-col');
  const catSelect = document.getElementById('analysis-category-col');
  const dateSelect = document.getElementById('analysis-date-col');

  if (targetSelect) {
    targetSelect.innerHTML = cols
      .filter(c => ['int', 'float'].includes(c.dtype) || ['currency', 'quantity', 'numeric', 'percentage'].includes(c.semantic_label))
      .map(c => `<option value="${c.name}">${c.name}</option>`).join('') ||
      cols.map(c => `<option value="${c.name}">${c.name}</option>`).join('');
  }

  if (catSelect) {
    catSelect.innerHTML = cols
      .map(c => `<option value="${c.name}">${c.name}</option>`).join('');
  }

  if (dateSelect) {
    const dateCols = cols.filter(c => c.dtype === 'datetime' || c.semantic_label === 'date');
    dateSelect.innerHTML = dateCols.map(c => `<option value="${c.name}">${c.name}</option>`).join('') +
      `<option value="">-- None --</option>`;
  }
}

async function handleAlignmentSubmit() {
  if (!state.fileId || !state.schema) return;

  showStatusBanner('Applying alignment configuration…', 'info');

  // Collect mappings
  const mappings = [];
  document.querySelectorAll('.mapping-row').forEach(row => {
    const source = row.dataset.source;
    const keep = row.querySelector('.mapping-keep-check').checked;
    const target = row.querySelector('.mapping-target-input').value.trim() || source;
    const type = row.querySelector('.mapping-type-select').value;

    mappings.push({
      source_column: source,
      target_field: target,
      target_type: type,
      keep: keep,
    });
  });

  // Collect filter rules
  const filters = [];
  document.querySelectorAll('.filter-row').forEach(row => {
    const col = row.querySelector('.filter-col-select').value;
    const op = row.querySelector('.filter-op-select').value;
    const val = row.querySelector('.filter-val-input').value.trim();

    if (op === 'not_null' || val) {
      filters.push({ column: col, operator: op, value: val });
    }
  });

  const alignConfig = {
    file_id: state.fileId,
    sheet_name: state.currentSheet,
    mappings: mappings,
    filters: filters,
    computed_columns: [],
  };

  try {
    const alignRes = await api.alignData(alignConfig);
    state.alignedResult = alignRes;

    showStatusBanner(`Aligned! ${alignRes.total_rows_aligned.toLocaleString()} rows kept.`, 'success');

    // Populate target dropdowns in Step 4 with aligned column names
    const metricSelect = document.getElementById('analysis-target-col');
    const categorySelect = document.getElementById('analysis-category-col');
    if (metricSelect) {
      metricSelect.innerHTML = alignRes.columns.map(c => `<option value="${c}">${c}</option>`).join('');
    }
    if (categorySelect) {
      categorySelect.innerHTML = alignRes.columns.map(c => `<option value="${c}">${c}</option>`).join('');
    }

    goToStep(4);
  } catch (err) {
    showStatusBanner(`Alignment error: ${err.message}`, 'error');
  }
}

function updateAnalysisOptionsUI() {
  const type = state.selectedAnalysisType;
  const compRow = document.getElementById('comp-type-row');
  if (compRow) {
    if (type === 'comparison' || type === 'sales_analysis') {
      compRow.classList.remove('hidden');
    } else {
      compRow.classList.add('hidden');
    }
  }
}

async function handleAnalysisSubmit() {
  if (!state.alignedResult) return;

  showStatusBanner('Running analysis calculation engine…', 'info');

  const metricCol = document.getElementById('analysis-target-col')?.value;
  const categoryCol = document.getElementById('analysis-category-col')?.value;
  const dateCol = document.getElementById('analysis-date-col')?.value;
  const compType = document.getElementById('analysis-comp-type')?.value;

  const req = {
    aligned_id: state.alignedResult.aligned_id,
    analysis_type: state.selectedAnalysisType,
    comparison_type: compType || 'none',
    target_columns: metricCol ? [metricCol] : [],
    category_columns: categoryCol ? [categoryCol] : [],
    date_column: dateCol || null,
    options: {},
  };

  try {
    const analysisRes = await api.analyzeData(req);
    state.analysisResult = analysisRes;

    // Render Results Dashboard (Step 5)
    document.getElementById('summary-text').textContent = analysisRes.summary;
    ui.renderKPICards(analysisRes.kpis);
    ui.renderCharts(analysisRes.charts);
    ui.renderAlignedPreviewTable(analysisRes.table_data, analysisRes.table_columns);

    showStatusBanner('Analysis generated successfully!', 'success');
    goToStep(5);
  } catch (err) {
    showStatusBanner(`Analysis error: ${err.message}`, 'error');
  }
}

function triggerExport(format) {
  if (!state.analysisResult && !state.alignedResult) return;
  const resId = state.analysisResult ? state.analysisResult.result_id : state.alignedResult.aligned_id;
  const url = api.getExportUrl(resId, format);
  window.open(url, '_blank');
}

function resetWizard() {
  state.fileId = null;
  state.schema = null;
  state.alignedResult = null;
  state.analysisResult = null;
  document.getElementById('file-input').value = '';
  document.getElementById('status-banner').innerHTML = '';
  goToStep(1);
}

function showStatusBanner(message, type = 'info') {
  const banner = document.getElementById('status-banner');
  if (!banner) return;

  const bgMap = {
    info: 'rgba(99, 102, 241, 0.15)',
    success: 'rgba(16, 185, 129, 0.15)',
    error: 'rgba(244, 63, 94, 0.2)',
  };
  const colorMap = {
    info: '#a5b4fc',
    success: '#6ee7b7',
    error: '#fecdd3',
  };

  banner.style.background = bgMap[type] || bgMap.info;
  banner.style.color = colorMap[type] || colorMap.info;
  banner.style.border = `1px solid ${colorMap[type]}`;
  banner.style.padding = '12px 18px';
  banner.style.borderRadius = '8px';
  banner.style.marginBottom = '20px';
  banner.style.fontSize = '0.9rem';
  banner.textContent = message;
}
