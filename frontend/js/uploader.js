/**
 * uploader.js — File drag-drop upload module (Stage 1 UI)
 *
 * Responsibilities:
 *   - Handle drag-over, drag-leave, drop events on the upload zone.
 *   - Handle file-input change event.
 *   - Validate file type/size client-side before posting.
 *   - POST to /upload, show progress, return parsed JSON result.
 *   - Expose: initUploader(onResult, onError, onProgress)
 */

const MAX_SIZE_MB  = 100;

export function initUploader({ onResult, onError, onProgress }) {
  const zone      = document.getElementById('upload-zone');
  const fileInput = document.getElementById('file-input');
  const browseBtn = document.getElementById('browse-btn');
  const progress  = document.getElementById('upload-progress');
  const progBar   = document.getElementById('prog-bar-fill');
  const progLabel = document.getElementById('prog-label');
  const statusBanner = document.getElementById('status-banner');

  // --- Drag events ---
  zone.addEventListener('dragover', e => {
    e.preventDefault();
    zone.classList.add('drag-over');
  });

  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));

  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  });

  browseBtn.addEventListener('click', () => fileInput.click());
  zone.addEventListener('click', e => {
    if (e.target === zone || e.target.closest('.upload-zone') && !e.target.closest('button'))
      fileInput.click();
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files[0]) handleFile(fileInput.files[0]);
  });

  // --- Core upload function ---
  async function handleFile(file) {
    const ext = '.' + file.name.split('.').pop().toLowerCase();

    // Accept any file up to MAX_SIZE_MB
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      showBanner('error', `❌ File too large (${(file.size/1048576).toFixed(1)} MB). Maximum is ${MAX_SIZE_MB} MB.`);
      return;
    }

    showBanner('info', `⏳ Uploading and analysing "${file.name}"...`);
    progress.classList.add('visible');
    setProgress(10, 'Uploading file…');
    onProgress && onProgress({ stage: 'uploading', pct: 10 });

    const formData = new FormData();
    formData.append('file', file);

    try {
      setProgress(30, 'Extracting data (Stage 1)…');

      const resp = await fetch('/upload', {
        method: 'POST',
        body: formData,
      });

      setProgress(70, 'Profiling data (Stage 2)…');

      if (!resp.ok) {
        let errMsg = `Server error ${resp.status}`;
        try { const errBody = await resp.json(); errMsg = errBody.detail || errMsg; }
        catch {}
        throw new Error(errMsg);
      }

      const data = await resp.json();
      setProgress(100, 'Complete!');

      setTimeout(() => {
        progress.classList.remove('visible');
        setProgress(0, '');
      }, 800);

      if (data.status === 'error') {
        showBanner('error', `❌ Processing failed: ${data.error}`);
        onError && onError(data.error);
      } else {
        showBanner('success', `✅ "${file.name}" processed successfully.`);
        onResult && onResult(data);
      }
    } catch (err) {
      setProgress(0, '');
      progress.classList.remove('visible');
      showBanner('error', `❌ ${err.message}`);
      onError && onError(err.message);
    }

    // Reset input so same file can be re-uploaded
    fileInput.value = '';
  }

  function setProgress(pct, label) {
    progBar.style.width = `${pct}%`;
    progLabel.textContent = label;
  }

  function showBanner(type, msg) {
    statusBanner.className = `status-banner visible ${type}`;
    statusBanner.innerHTML = `<span>${msg}</span>`;
  }
}
