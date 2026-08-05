/**
 * export_trigger.js — Stage 5 export button wiring
 *
 * Renders an export action bar and wires the XLSX / PDF / CSV download buttons.
 * Downloads are triggered via a hidden <a> link (no page navigation, works in all browsers).
 *
 * Exports:
 *   buildExportBar(taskId) → HTMLElement
 */

/**
 * Build the export action bar for a given task.
 * @param {string} taskId - the pipeline task ID returned by /upload
 * @returns {HTMLElement}
 */
export function buildExportBar(taskId) {
  const bar = document.createElement('div');
  bar.className = 'export-bar';
  bar.setAttribute('role', 'toolbar');
  bar.setAttribute('aria-label', 'Export options');

  const label = document.createElement('span');
  label.className = 'export-bar-label';
  label.textContent = '📤 Export:';
  bar.appendChild(label);

  const formats = [
    { fmt: 'xlsx', icon: '📊', label: 'XLSX', cls: 'xlsx', title: 'Download as Excel workbook (.xlsx) — includes =SUM() formulas for computed columns' },
    { fmt: 'pdf',  icon: '📄', label: 'PDF',  cls: 'pdf',  title: 'Download as PDF report' },
    { fmt: 'csv',  icon: '📋', label: 'CSV',  cls: 'csv',  title: 'Download as flat CSV (detail rows only)' },
  ];

  formats.forEach(({ fmt, icon, label: btnLabel, cls, title }) => {
    const btn = document.createElement('button');
    btn.className = `btn-export ${cls}`;
    btn.id = `export-btn-${fmt}`;
    btn.type = 'button';
    btn.title = title;
    btn.innerHTML = `${icon} ${btnLabel}`;

    btn.addEventListener('click', async () => {
      btn.disabled = true;
      const origHTML = btn.innerHTML;
      btn.innerHTML = `⏳ Preparing…`;

      try {
        const url = `/export/${encodeURIComponent(taskId)}/${fmt}`;
        // Trigger download via a temporary anchor
        const a = document.createElement('a');
        a.href = url;
        a.download = '';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);

        // Brief delay to show "Preparing" feedback, then restore
        setTimeout(() => {
          btn.innerHTML = `✅ Done`;
          setTimeout(() => {
            btn.innerHTML = origHTML;
            btn.disabled = false;
          }, 1500);
        }, 800);
      } catch (err) {
        btn.innerHTML = `❌ Error`;
        setTimeout(() => {
          btn.innerHTML = origHTML;
          btn.disabled = false;
        }, 2000);
        console.error(`[GeniusDataManager] Export ${fmt} failed:`, err);
      }
    });

    bar.appendChild(btn);
  });

  return bar;
}
