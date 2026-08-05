/**
 * app.js — GeniusDataManager Phase B entry point
 *
 * Wires together:
 *   - uploader.js     (file upload + progress)
 *   - profile_viewer.js (Stage 2 profile display)
 *   - dashboard_builder.js (Stage 3 layout + Stage 4 dashboard)
 *
 * Export buttons (Stage 5) are wired inside dashboard_builder → export_trigger.js.
 */

import { initUploader } from './uploader.js';
import { renderProfile } from './profile_viewer.js';
import { renderDashboard } from './dashboard_builder.js';

document.addEventListener('DOMContentLoaded', () => {
  initUploader({
    onResult: async (pipelineResult) => {
      // Stage 2: render profile immediately
      renderProfile(pipelineResult);
      document.getElementById('profile-section').scrollIntoView({ behavior: 'smooth', block: 'start' });

      // Stages 3 + 4: plan layout and render dashboard below the profile
      await renderDashboard(pipelineResult);
    },
    onError: (msg) => {
      console.error('[GeniusDataManager] Upload/processing error:', msg);
    },
    onProgress: ({ stage, pct }) => {
      console.log(`[GeniusDataManager] ${stage}: ${pct}%`);
    },
  });
});
