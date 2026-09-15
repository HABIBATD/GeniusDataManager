/**
 * API Client module for GeniusDataManager.
 */

const API_BASE = '/api';

export async function uploadFile(file) {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${API_BASE}/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errData.detail || 'File upload failed.');
  }

  return await res.json();
}

export async function getSchema(fileId, sheetName = null) {
  let url = `${API_BASE}/schema/${fileId}`;
  if (sheetName) {
    url += `?sheet=${encodeURIComponent(sheetName)}`;
  }

  const res = await fetch(url);
  if (!res.ok) {
    const errData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errData.detail || 'Failed to fetch schema.');
  }

  return await res.json();
}

export async function alignData(alignmentConfig) {
  const res = await fetch(`${API_BASE}/align`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(alignmentConfig),
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errData.detail || 'Alignment failed.');
  }

  return await res.json();
}

export async function analyzeData(analysisRequest) {
  const res = await fetch(`${API_BASE}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(analysisRequest),
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errData.detail || 'Analysis calculation failed.');
  }

  return await res.json();
}

export function getExportUrl(resultId, format = 'csv') {
  return `${API_BASE}/export/${resultId}?format=${format}`;
}
