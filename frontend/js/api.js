/**
 * API Client module for GeniusDataManager.
 */

// Dynamically resolve API_BASE so it works whether served by FastAPI or Live Server
const API_BASE = (typeof window !== 'undefined' && (window.location.protocol === 'file:' || (window.location.port && window.location.port !== '8000')))
  ? `http://${window.location.hostname || '127.0.0.1'}:8000/api`
  : '/api';

async function safeFetch(url, options = {}) {
  try {
    return await fetch(url, options);
  } catch (err) {
    throw new Error(`Cannot connect to backend server at ${url}. Please ensure 'python start.py' is running.`);
  }
}

export async function uploadFile(file) {
  const formData = new FormData();
  formData.append('file', file);

  const res = await safeFetch(`${API_BASE}/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errData.detail || errData.message || 'File upload failed.');
  }

  return await res.json();
}

export async function getSchema(fileId, sheetName = null) {
  let url = `${API_BASE}/schema/${fileId}`;
  if (sheetName) {
    url += `?sheet=${encodeURIComponent(sheetName)}`;
  }

  const res = await safeFetch(url);
  if (!res.ok) {
    const errData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errData.detail || errData.message || 'Failed to fetch schema.');
  }

  return await res.json();
}

export async function alignData(alignmentConfig) {
  const res = await safeFetch(`${API_BASE}/align`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(alignmentConfig),
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errData.detail || errData.message || 'Alignment failed.');
  }

  return await res.json();
}

export async function analyzeData(analysisRequest) {
  const res = await safeFetch(`${API_BASE}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(analysisRequest),
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errData.detail || errData.message || 'Analysis calculation failed.');
  }

  return await res.json();
}

export function getExportUrl(resultId, format = 'csv') {
  return `${API_BASE}/export/${resultId}?format=${format}`;
}

