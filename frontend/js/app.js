/**
 * SAFEGUARD AI - Main Controller
 * Handles real-time telemetry, API monitoring, Online/Offline engine switching,
 * and Worker Inspection Reports (with snapshots & CSV export).
 */

import { TelemetryWebSocket } from './websocket.js';
import { HUDOverlay } from './hud_overlay.js';
import { APDVisualizer } from './apd_card.js';

document.addEventListener('DOMContentLoaded', () => {
  // Elements: Header Telemetry
  const wsStatusDot = document.getElementById('ws-status-dot');
  const wsStatusText = document.getElementById('ws-status-text');
  const fpsText = document.getElementById('fps-counter');
  const apiStatusDot = document.getElementById('api-status-dot');
  const apiStatusText = document.getElementById('api-status-text');
  const apiMonitorBadge = document.getElementById('api-monitor-badge');
  const btnModeToggle = document.getElementById('btn-mode-toggle');
  const modeIcon = document.getElementById('mode-icon');
  const modeText = document.getElementById('mode-text');

  // Elements: Video & Overlays
  const canvasElement = document.getElementById('hud-canvas');
  const liveVideoImg = document.getElementById('live-stream');

  // Elements: Main Header Actions
  const btnOpenReports = document.getElementById('btn-open-reports');
  const btnReset = document.getElementById('btn-reset');
  const btnSettings = document.getElementById('btn-settings');

  // Elements: Settings Modal
  const modalSettings = document.getElementById('settings-modal');
  const btnCloseModal = document.getElementById('btn-close-modal');
  const btnSaveKey = document.getElementById('btn-save-key');
  const inputApiKey = document.getElementById('input-gemini-key');

  // Elements: Reports Modal
  const modalReports = document.getElementById('reports-modal');
  const btnCloseReports = document.getElementById('btn-close-reports');
  const btnRefreshReports = document.getElementById('btn-refresh-reports');
  const btnExportCsv = document.getElementById('btn-export-csv');
  const reportsTableBody = document.getElementById('reports-table-body');
  const kpiTotal = document.getElementById('kpi-total');
  const kpiComplete = document.getElementById('kpi-complete');
  const kpiViolations = document.getElementById('kpi-violations');
  const kpiRate = document.getElementById('kpi-rate');
  const filterTabs = document.querySelectorAll('.tab-btn');

  // Elements: Snapshot Modal
  const modalSnapshot = document.getElementById('snapshot-modal');
  const btnCloseSnapshot = document.getElementById('btn-close-snapshot');
  const snapshotImg = document.getElementById('snapshot-modal-img');
  const snapshotCaption = document.getElementById('snapshot-modal-caption');

  // Backend Endpoints
  const backendHost = window.location.hostname || 'localhost';
  let portSuffix = '';
  if (window.location.port) {
    portSuffix = `:${window.location.port}`;
  } else if (window.location.protocol === 'file:' || backendHost === 'localhost' || backendHost === '127.0.0.1') {
    portSuffix = ':8000';
  }
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const httpProtocol = window.location.protocol === 'https:' ? 'https:' : 'http:';

  const wsUrl = `${wsProtocol}//${backendHost}${portSuffix}/ws`;
  const streamUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/stream`;
  const resetUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/reset`;
  const configKeyUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/config/gemini-key`;
  const engineModeUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/config/engine-mode`;
  const reportsUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/reports`;
  const exportCsvUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/reports/export`;
  const pingUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/monitoring/ping`;

  // Active state
  let currentEngineMode = 'HYBRID_AUTO';
  let currentFilter = 'all';

  // Set stream source
  liveVideoImg.src = streamUrl;

  // Initialize components
  const hud = new HUDOverlay(canvasElement);
  const visualizer = new APDVisualizer();

  // --- WEBSOCKET TELEMETRY LISTENER ---
  const ws = new TelemetryWebSocket(
    wsUrl,
    (telemetry) => {
      // 1. Update FPS
      if (telemetry.fps !== undefined) {
        fpsText.textContent = `${telemetry.fps} FPS`;
      }

      // 2. Update API Health & Jam Monitoring
      if (telemetry.api_monitor) {
        updateApiMonitorUI(telemetry.api_monitor, telemetry.is_live_gemini);
      }

      // 3. Update Online/Offline Mode UI
      if (telemetry.engine_mode && telemetry.engine_mode !== currentEngineMode) {
        currentEngineMode = telemetry.engine_mode;
        updateEngineModeUI(currentEngineMode);
      }

      // 4. Render Canvas HUD with frame dimensions and corridor guides
      if (telemetry.frame_width && telemetry.frame_height) {
        hud.setFrameDimensions(telemetry.frame_width, telemetry.frame_height);
      }
      if (telemetry.corridor) {
        hud.setCorridor(telemetry.corridor);
      }
      hud.setDetections(telemetry.detections);

      // 5. Update APD Visualizer (Cards, Tower Light, Hero Banner, Log)
      visualizer.update(telemetry);
    },
    (status) => {
      if (status === 'connected') {
        wsStatusDot.className = 'dot-indicator connected';
        wsStatusText.textContent = 'ONLINE';
      } else {
        wsStatusDot.className = 'dot-indicator danger';
        wsStatusText.textContent = 'DISCONNECTED';
      }
    }
  );

  // --- API MONITOR UI UPDATER ---
  function updateApiMonitorUI(monitor, isLiveGemini) {
    const status = monitor.status;
    const latency = monitor.latency_ms;

    if (monitor.engine_mode === 'FORCE_LOCAL') {
      apiStatusDot.className = 'dot-indicator';
      apiStatusDot.style.background = 'var(--color-amber)';
      apiStatusText.textContent = 'API: MODE OFFLINE';
      return;
    }

    if (!isLiveGemini || status === 'OFFLINE') {
      apiStatusDot.className = 'dot-indicator danger';
      apiStatusText.textContent = 'API: OFFLINE / NO KEY';
    } else if (status === 'DEGRADED') {
      apiStatusDot.className = 'dot-indicator warning';
      apiStatusText.textContent = `API: MACET (${latency}ms)`;
    } else {
      apiStatusDot.className = 'dot-indicator connected';
      apiStatusText.textContent = `API: ONLINE (${latency}ms)`;
    }
  }

  // --- ENGINE MODE UI UPDATER ---
  function updateEngineModeUI(mode) {
    if (mode === 'FORCE_LOCAL') {
      btnModeToggle.classList.add('mode-local');
      modeIcon.textContent = '⚡';
      modeText.textContent = 'OFFLINE: LOKAL GPU';
    } else {
      btnModeToggle.classList.remove('mode-local');
      modeIcon.textContent = '🌐';
      modeText.textContent = 'ONLINE: CLOUD VLM';
    }
  }

  // --- ENGINE MODE TOGGLE ACTION ---
  btnModeToggle.addEventListener('click', async () => {
    const nextMode = currentEngineMode === 'FORCE_LOCAL' ? 'HYBRID_AUTO' : 'FORCE_LOCAL';
    try {
      btnModeToggle.disabled = true;
      const res = await fetch(engineModeUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ engine_mode: nextMode })
      });
      const data = await res.json();
      currentEngineMode = data.engine_mode;
      updateEngineModeUI(currentEngineMode);
    } catch (e) {
      console.error('Failed to toggle engine mode:', e);
    } finally {
      btnModeToggle.disabled = false;
    }
  });

  // --- ON-DEMAND API LATENCY PING ---
  apiMonitorBadge.addEventListener('click', async () => {
    try {
      apiStatusText.textContent = 'MENGUJI PING...';
      const res = await fetch(pingUrl, { method: 'POST' });
      const data = await res.json();
      if (data.status === 'ONLINE') {
        alert(`✅ Gemini Cloud API Responsif!\nLatensi: ${data.latency_ms} ms\nStatus: ${data.status}`);
      } else {
        alert(`⚠️ Hasil Ping API:\nStatus: ${data.status}\nLatensi: ${data.latency_ms} ms\nPesan: ${data.message || data.reply || '-'}`);
      }
    } catch (e) {
      alert(`❌ Gagal menghubungi server backend: ${e}`);
    }
  });

  // --- RESET TRACKING ACTION ---
  btnReset.addEventListener('click', async () => {
    try {
      btnReset.disabled = true;
      btnReset.textContent = 'Mereset...';
      await fetch(resetUrl, { method: 'POST' });
      setTimeout(() => {
        btnReset.disabled = false;
        btnReset.innerHTML = '🔄 Reset';
      }, 500);
    } catch (e) {
      console.error('Failed to reset:', e);
      btnReset.disabled = false;
      btnReset.innerHTML = '🔄 Reset';
    }
  });

  // --- SETTINGS MODAL ---
  btnSettings.addEventListener('click', () => modalSettings.classList.add('open'));
  btnCloseModal.addEventListener('click', () => modalSettings.classList.remove('open'));
  modalSettings.addEventListener('click', (e) => {
    if (e.target === modalSettings) modalSettings.classList.remove('open');
  });

  btnSaveKey.addEventListener('click', async () => {
    const key = inputApiKey.value.trim();
    if (!key) {
      alert('Silakan masukkan Gemini API Key terlebih dahulu.');
      return;
    }
    try {
      btnSaveKey.disabled = true;
      btnSaveKey.textContent = 'Menyimpan...';
      const res = await fetch(configKeyUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: key })
      });
      const data = await res.json();
      if (data.status === 'success') {
        alert('API Key berhasil disimpan di server-side! Gemini Live aktif.');
        modalSettings.classList.remove('open');
        inputApiKey.value = '';
      } else {
        alert('Gagal menyimpan API Key: ' + data.message);
      }
    } catch (err) {
      alert('Koneksi ke server gagal: ' + err);
    } finally {
      btnSaveKey.disabled = false;
      btnSaveKey.textContent = 'Simpan ke Server';
    }
  });

  // --- WORKER REPORTS MODAL & DATA FETCHER ---
  btnOpenReports.addEventListener('click', () => {
    modalReports.classList.add('open');
    loadReports(currentFilter);
  });

  btnCloseReports.addEventListener('click', () => modalReports.classList.remove('open'));
  modalReports.addEventListener('click', (e) => {
    if (e.target === modalReports) modalReports.classList.remove('open');
  });

  btnRefreshReports.addEventListener('click', () => loadReports(currentFilter));

  // Filter tabs
  filterTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      filterTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      currentFilter = tab.getAttribute('data-filter');
      loadReports(currentFilter);
    });
  });

  // Download CSV
  btnExportCsv.addEventListener('click', () => {
    window.location.href = exportCsvUrl;
  });

  async function loadReports(statusFilter = 'all') {
    reportsTableBody.innerHTML = `
      <tr>
        <td colspan="7" style="text-align:center; padding:2rem; color:var(--text-muted);">
          Memuat data riwayat pemeriksaan pekerja...
        </td>
      </tr>
    `;

    try {
      const res = await fetch(`${reportsUrl}?limit=50&status=${statusFilter}`);
      const data = await res.json();

      // Update KPI Cards
      kpiTotal.textContent = data.total_all || 0;
      kpiComplete.textContent = data.complete_count || 0;
      kpiViolations.textContent = data.violation_count || 0;
      kpiRate.textContent = `${data.compliance_rate || 100}%`;

      const records = data.page_records || [];
      if (records.length === 0) {
        reportsTableBody.innerHTML = `
          <tr>
            <td colspan="7" style="text-align:center; padding:2rem; color:var(--text-muted);">
              Belum ada data pemeriksaan yang tercatat.
            </td>
          </tr>
        `;
        return;
      }

      // Render Table Rows
      reportsTableBody.innerHTML = records.map(rec => {
        const isComplete = rec.is_complete;
        const statusBadge = isComplete 
          ? '<span class="apd-status-badge badge-green">LENGKAP</span>' 
          : '<span class="apd-status-badge badge-red">DITOLAK</span>';

        // Snapshot image
        let snapshotHtml = '<div style="width:48px; height:48px; background:#182033; border-radius:6px; display:flex; align-items:center; justify-content:center; color:#64748b; font-size:0.75rem;">N/A</div>';
        if (rec.snapshot_filename) {
          const imgUrl = `${httpProtocol}//${backendHost}:${backendPort}/api/reports/snapshots/${rec.snapshot_filename}`;
          snapshotHtml = `
            <img src="${imgUrl}" class="worker-thumb" alt="Pekerja #${rec.track_id}"
                 title="Klik untuk perbesar foto"
                 data-full="${imgUrl}"
                 data-caption="Pekerja #${rec.track_id} - ${rec.time_str} (${isComplete ? 'LENGKAP' : 'DITOLAK'})"
            />
          `;
        }

        // APD Checklist Badges
        const helmBadge = rec.helm_detected 
          ? '<span class="apd-mini-badge apd-mini-ok">🪖 Helm ✓</span>' 
          : '<span class="apd-mini-badge apd-mini-bad">🪖 Helm ✗</span>';
        const rompiBadge = rec.rompi_valid 
          ? `<span class="apd-mini-badge apd-mini-ok">🦺 Rompi (${rec.rompi_color}) ✓</span>` 
          : '<span class="apd-mini-badge apd-mini-bad">🦺 Rompi ✗</span>';
        const celanaBadge = rec.celana_detected 
          ? '<span class="apd-mini-badge apd-mini-ok">👖 Celana ✓</span>' 
          : '<span class="apd-mini-badge apd-mini-bad">👖 Celana ✗</span>';
        const sepatuBadge = rec.sepatu_closed 
          ? '<span class="apd-mini-badge apd-mini-ok">👟 Sepatu ✓</span>' 
          : '<span class="apd-mini-badge apd-mini-bad">👟 Sepatu ✗</span>';

        const sourceIcon = (rec.inference_source || '').includes('GEMINI') ? '🌐 Gemini' : '⚡ GPU Lokal';
        const notesText = rec.missing_items && rec.missing_items.length > 0 
          ? `<span style="color:var(--color-red);">Belum memakai: ${rec.missing_items.join(', ')}</span>`
          : `<span style="color:var(--color-green);">Kepatuhan 100% K3</span>`;

        return `
          <tr>
            <td>${snapshotHtml}</td>
            <td style="font-family:var(--font-mono); font-size:0.78rem;">
              <div>${rec.date_str}</div>
              <div style="color:var(--text-muted);">${rec.time_str}</div>
            </td>
            <td>
              <strong style="color:var(--text-primary);">Pekerja #${rec.track_id}</strong>
            </td>
            <td>${statusBadge}</td>
            <td>
              <div>${helmBadge} ${rompiBadge}</div>
              <div>${celanaBadge} ${sepatuBadge}</div>
            </td>
            <td style="font-family:var(--font-mono); font-size:0.75rem; color:var(--text-secondary);">
              <div>${sourceIcon}</div>
              <div>${rec.inference_time_ms} ms</div>
            </td>
            <td style="font-size:0.8rem;">
              ${notesText}
            </td>
          </tr>
        `;
      }).join('');

      // Add click listeners to thumbnail preview
      const thumbs = reportsTableBody.querySelectorAll('.worker-thumb');
      thumbs.forEach(thumb => {
        thumb.addEventListener('click', () => {
          const fullSrc = thumb.getAttribute('data-full');
          const caption = thumb.getAttribute('data-caption');
          snapshotImg.src = fullSrc;
          snapshotCaption.textContent = caption;
          modalSnapshot.classList.add('open');
        });
      });

    } catch (e) {
      reportsTableBody.innerHTML = `
        <tr>
          <td colspan="7" style="text-align:center; padding:2rem; color:var(--color-red);">
            Gagal memuat data laporan: ${e}
          </td>
        </tr>
      `;
    }
  }

  // --- SNAPSHOT PREVIEW MODAL CLOSE ---
  btnCloseSnapshot.addEventListener('click', () => modalSnapshot.classList.remove('open'));
  modalSnapshot.addEventListener('click', (e) => {
    if (e.target === modalSnapshot) modalSnapshot.classList.remove('open');
  });

});
