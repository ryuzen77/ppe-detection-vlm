/**
 * SAFEGUARD AI - Main Controller
 * Handles SPA 3-Tab navigation (Monitoring, Laporan, Pengaturan),
 * real-time telemetry, video toolbar controls, integrated report auditing,
 * and IoT hardware / AI settings.
 */

import { TelemetryWebSocket } from './websocket.js';
import { HUDOverlay } from './hud_overlay.js';
import { APDVisualizer } from './apd_card.js';

document.addEventListener('DOMContentLoaded', () => {
  // --- 1. DOM ELEMENT REFERENCES ---

  // Navigation Tabs
  const navTabs = {
    monitoring: document.getElementById('nav-tab-monitoring'),
    reports: document.getElementById('nav-tab-reports'),
    settings: document.getElementById('nav-tab-settings')
  };

  const views = {
    monitoring: document.getElementById('view-monitoring'),
    reports: document.getElementById('view-reports'),
    settings: document.getElementById('view-settings')
  };

  const btnSeeAllReports = document.getElementById('btn-see-all-reports');

  // Ribbon Telemetry Indicators
  const dotCamera = document.getElementById('dot-camera');
  const ribbonCameraText = document.getElementById('ribbon-camera-text');
  const dotAi = document.getElementById('dot-ai');
  const ribbonAiText = document.getElementById('ribbon-ai-text');
  const btnRibbonCloud = document.getElementById('btn-ribbon-cloud');
  const ribbonCloudText = document.getElementById('ribbon-cloud-text');
  const fpsText = document.getElementById('fps-counter');

  // Video Viewport & Canvas
  const canvasElement = document.getElementById('hud-canvas');
  const liveVideoImg = document.getElementById('live-stream');
  const hudSubjectBadge = document.getElementById('hud-subject-badge');

  // Video Toolbar Controls
  const toggleCorridorGuide = document.getElementById('toggle-corridor-guide');
  const toggleAudioMute = document.getElementById('toggle-audio-mute');
  const audioSwitchLabel = document.getElementById('audio-switch-label');
  const btnToggleTechDetails = document.getElementById('btn-toggle-tech-details');
  const techDetailsDrawer = document.getElementById('tech-details-drawer');
  const techChevron = document.getElementById('tech-chevron');
  const btnResetInspection = document.getElementById('btn-reset-inspection');

  // Technical Drawer Fields
  const techEngineMode = document.getElementById('tech-engine-mode');
  const techLatencyMs = document.getElementById('tech-latency-ms');
  const techActiveTrack = document.getElementById('tech-active-track');
  const techStability = document.getElementById('tech-stability');

  // Reports View Elements
  const kpiTotal = document.getElementById('kpi-total');
  const kpiComplete = document.getElementById('kpi-complete');
  const kpiViolations = document.getElementById('kpi-violations');
  const kpiRate = document.getElementById('kpi-rate');
  const filterButtons = {
    all: document.getElementById('filter-all'),
    complete: document.getElementById('filter-complete'),
    incomplete: document.getElementById('filter-incomplete')
  };
  const filterDateInput = document.getElementById('filter-date-input');
  const btnRefreshReports = document.getElementById('btn-refresh-reports');
  const btnExportCsv = document.getElementById('btn-export-csv');
  const reportsTableBody = document.getElementById('reports-table-body');

  // Snapshot Full Preview Modal
  const modalSnapshot = document.getElementById('snapshot-modal');
  const btnCloseSnapshot = document.getElementById('btn-close-snapshot');
  const snapshotImg = document.getElementById('snapshot-modal-img');
  const snapshotCaption = document.getElementById('snapshot-modal-caption');

  // Settings View Elements
  const btnTestGreen = document.getElementById('btn-test-green');
  const btnTestRed = document.getElementById('btn-test-red');
  const btnTestOff = document.getElementById('btn-test-off');
  const inputGeminiKey = document.getElementById('input-gemini-key');
  const btnPingGemini = document.getElementById('btn-ping-gemini');
  const btnSaveSettings = document.getElementById('btn-save-settings');

  // --- 2. BACKEND API ENDPOINTS ---
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
  const iotTestUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/iot/test`;
  const audioConfigUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/config/audio`;

  // Active Controller State
  let currentEngineMode = 'HYBRID_AUTO';
  let currentStatusFilter = 'all';
  let currentDateFilter = '';

  // Initialize live video stream source
  if (liveVideoImg) {
    liveVideoImg.src = streamUrl;
  }

  // Initialize Canvas HUD and Visualizer
  const hud = new HUDOverlay(canvasElement);
  const visualizer = new APDVisualizer();

  // --- 3. TAB NAVIGATION CONTROLLER ---
  function switchTab(targetTab) {
    // Update active tab buttons
    Object.keys(navTabs).forEach((key) => {
      if (navTabs[key]) {
        if (key === targetTab) {
          navTabs[key].classList.add('active');
        } else {
          navTabs[key].classList.remove('active');
        }
      }
    });

    // Update active views
    Object.keys(views).forEach((key) => {
      if (views[key]) {
        if (key === targetTab) {
          views[key].style.display = '';
          views[key].classList.add('active');
        } else {
          views[key].style.display = 'none';
          views[key].classList.remove('active');
        }
      }
    });

    // If switching to reports, automatically fetch latest data
    if (targetTab === 'reports') {
      loadReports();
    }
  }

  // Attach Tab Click Listeners
  if (navTabs.monitoring) navTabs.monitoring.addEventListener('click', () => switchTab('monitoring'));
  if (navTabs.reports) navTabs.reports.addEventListener('click', () => switchTab('reports'));
  if (navTabs.settings) navTabs.settings.addEventListener('click', () => switchTab('settings'));
  if (btnSeeAllReports) btnSeeAllReports.addEventListener('click', () => switchTab('reports'));

  // --- 4. VIDEO TOOLBAR CONTROLS ---

  // Toggle Corridor Guide Lines & Footprint Zone
  if (toggleCorridorGuide) {
    toggleCorridorGuide.addEventListener('change', (e) => {
      hud.setGuidesVisible(e.target.checked);
    });
  }

  // Toggle Audio Mute Switch
  if (toggleAudioMute) {
    toggleAudioMute.checked = true; // default: sound on
    toggleAudioMute.addEventListener('change', async (e) => {
      const isMuted = !e.target.checked;
      if (audioSwitchLabel) {
        audioSwitchLabel.textContent = isMuted ? '🔇 Senyap' : '🔊 Suara';
      }
      try {
        await fetch(audioConfigUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ muted: isMuted })
        });
      } catch (err) {
        console.error('Failed to toggle audio mute:', err);
      }
    });
  }

  // Toggle Technical Details Drawer
  if (btnToggleTechDetails && techDetailsDrawer) {
    btnToggleTechDetails.addEventListener('click', () => {
      const isOpen = techDetailsDrawer.classList.toggle('open');
      if (techChevron) {
        techChevron.style.transform = isOpen ? 'rotate(180deg)' : 'rotate(0deg)';
      }
    });
  }

  // Reset Subject Inspection
  if (btnResetInspection) {
    btnResetInspection.addEventListener('click', async () => {
      try {
        btnResetInspection.disabled = true;
        btnResetInspection.innerHTML = '<span>⏳</span> Mereset...';
        await fetch(resetUrl, { method: 'POST' });
        setTimeout(() => {
          btnResetInspection.disabled = false;
          btnResetInspection.innerHTML = '<span>🔄</span> Mulai ulang';
        }, 500);
      } catch (e) {
        console.error('Failed to reset inspection:', e);
        btnResetInspection.disabled = false;
        btnResetInspection.innerHTML = '<span>🔄</span> Mulai ulang';
      }
    });
  }

  // --- 5. REAL-TIME WEBSOCKET TELEMETRY LISTENER ---
  const ws = new TelemetryWebSocket(
    wsUrl,
    (telemetry) => {
      // 0. Sync Audio Mute Switch
      if (telemetry.audio_muted !== undefined && toggleAudioMute) {
        const isMuted = telemetry.audio_muted;
        if (toggleAudioMute.checked === isMuted) {
          toggleAudioMute.checked = !isMuted;
          if (audioSwitchLabel) {
            audioSwitchLabel.textContent = isMuted ? '🔇 Senyap' : '🔊 Suara';
          }
        }
      }

      // 1. Update FPS Display
      if (fpsText && telemetry.fps !== undefined) {
        fpsText.textContent = `${Number(telemetry.fps).toFixed(1).replace('.', ',')} FPS`;
      }

      // 2. Update Status Ribbon & Engine Mode
      if (telemetry.api_monitor) {
        updateRibbonCloudUI(telemetry.api_monitor, telemetry.is_live_gemini);
      }
      if (telemetry.engine_mode && telemetry.engine_mode !== currentEngineMode) {
        currentEngineMode = telemetry.engine_mode;
        if (techEngineMode) techEngineMode.textContent = currentEngineMode;
      }

      // 3. Update Technical Drawer Fields
      if (techLatencyMs) {
        techLatencyMs.textContent = telemetry.vlm_latency_ms ? `${telemetry.vlm_latency_ms} ms` : '0 ms';
      }
      const activeDet = (telemetry.detections || []).find(d => d.track_id === telemetry.active_track_id);
      if (techActiveTrack) {
        techActiveTrack.textContent = telemetry.active_track_id ? `#${telemetry.active_track_id}` : 'None';
      }
      if (techStability) {
        const stabCount = activeDet ? (activeDet.stability_count || 0) : 0;
        techStability.textContent = `${stabCount} / 2`;
      }

      // Update Subject Tracking Badge in Video Viewport
      if (hudSubjectBadge) {
        if (telemetry.active_track_id) {
          hudSubjectBadge.textContent = `Subjek #${telemetry.active_track_id}`;
          hudSubjectBadge.style.display = 'block';
        } else {
          hudSubjectBadge.textContent = 'Menunggu Subjek';
        }
      }

      // 4. Render Canvas HUD with Frame Dimensions & Corridor Guides
      if (telemetry.frame_width && telemetry.frame_height) {
        hud.setFrameDimensions(telemetry.frame_width, telemetry.frame_height);
      }
      if (telemetry.corridor) {
        hud.setCorridor(telemetry.corridor);
      }
      hud.setDetections(telemetry.detections);

      // 5. Update APD Visualizer (Stepper, Guidance, 4-Item Badges, Recent History)
      visualizer.update(telemetry);
    },
    (status) => {
      if (dotCamera && ribbonCameraText) {
        if (status === 'connected') {
          dotCamera.className = 'status-dot green';
          ribbonCameraText.textContent = 'Kamera aktif';
        } else {
          dotCamera.className = 'status-dot red';
          ribbonCameraText.textContent = 'Kamera terputus';
        }
      }
    }
  );

  // Update Cloud Status in Top Ribbon
  function updateRibbonCloudUI(monitor, isLiveGemini) {
    if (!ribbonCloudText) return;

    if (monitor.engine_mode === 'FORCE_LOCAL') {
      ribbonCloudText.textContent = 'Cloud: Mode Offline (Lokal GPU)';
      if (btnRibbonCloud) btnRibbonCloud.style.color = 'var(--accent-amber)';
      return;
    }

    if (isLiveGemini && monitor.status === 'ONLINE') {
      ribbonCloudText.textContent = `Cloud terhubung (Gemini ${monitor.latency_ms || 0}ms)`;
      if (btnRibbonCloud) btnRibbonCloud.style.color = 'var(--accent-green)';
    } else if (monitor.status === 'DEGRADED') {
      ribbonCloudText.textContent = `Cloud lambat (${monitor.latency_ms || 0}ms)`;
      if (btnRibbonCloud) btnRibbonCloud.style.color = 'var(--accent-amber)';
    } else {
      ribbonCloudText.textContent = 'Cloud opsional: tidak terhubung';
      if (btnRibbonCloud) btnRibbonCloud.style.color = 'var(--text-muted)';
    }
  }

  // Toggle Cloud vs Local Mode on Ribbon Click
  if (btnRibbonCloud) {
    btnRibbonCloud.addEventListener('click', async () => {
      const nextMode = currentEngineMode === 'FORCE_LOCAL' ? 'HYBRID_AUTO' : 'FORCE_LOCAL';
      try {
        const res = await fetch(engineModeUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ engine_mode: nextMode })
        });
        const data = await res.json();
        currentEngineMode = data.engine_mode;
        if (techEngineMode) techEngineMode.textContent = currentEngineMode;
        alert(`Mode Engine berhasil diubah ke: ${currentEngineMode === 'FORCE_LOCAL' ? 'Lokal GPU (100% Offline)' : 'Hybrid Cloud Gemini'}`);
      } catch (e) {
        console.error('Failed to toggle engine mode:', e);
      }
    });
  }

  // --- 6. INTEGRATED LAPORAN (REPORTS) CONTROLLER ---

  // Filter Buttons (Semua / Lengkap / Pelanggaran)
  Object.keys(filterButtons).forEach((key) => {
    const btn = filterButtons[key];
    if (btn) {
      btn.addEventListener('click', () => {
        Object.values(filterButtons).forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentStatusFilter = btn.getAttribute('data-filter') || 'all';
        loadReports();
      });
    }
  });

  // Date Filter Picker
  if (filterDateInput) {
    filterDateInput.addEventListener('change', () => {
      currentDateFilter = filterDateInput.value.trim();
      loadReports();
    });
  }

  // Refresh Button
  if (btnRefreshReports) {
    btnRefreshReports.addEventListener('click', () => loadReports());
  }

  // Download CSV Export
  if (btnExportCsv) {
    btnExportCsv.addEventListener('click', () => {
      window.location.href = exportCsvUrl;
    });
  }

  // Fetch and Render Reports Table
  async function loadReports() {
    if (!reportsTableBody) return;

    reportsTableBody.innerHTML = `
      <tr>
        <td colspan="7" class="table-loading-cell">
          Memuat data riwayat pemeriksaan pekerja...
        </td>
      </tr>
    `;

    try {
      let queryUrl = `${reportsUrl}?limit=50&status=${currentStatusFilter}`;
      if (currentDateFilter) {
        queryUrl += `&date=${encodeURIComponent(currentDateFilter)}`;
      }

      const res = await fetch(queryUrl);
      const data = await res.json();

      // Update KPI Statistics
      if (kpiTotal) kpiTotal.textContent = data.total_all || 0;
      if (kpiComplete) kpiComplete.textContent = data.complete_count || 0;
      if (kpiViolations) kpiViolations.textContent = data.violation_count || 0;
      if (kpiRate) kpiRate.textContent = `${data.compliance_rate || 100}%`;

      const records = data.page_records || [];
      if (records.length === 0) {
        reportsTableBody.innerHTML = `
          <tr>
            <td colspan="7" style="text-align:center; padding:2.5rem; color:var(--text-muted);">
              Tidak ada data riwayat pemeriksaan yang sesuai dengan filter.
            </td>
          </tr>
        `;
        return;
      }

      // Render Records Rows
      reportsTableBody.innerHTML = records.map(rec => {
        const isComplete = rec.is_complete;
        const statusBadge = isComplete 
          ? '<span class="status-pill status-pill-success">✅ Lolos</span>' 
          : '<span class="status-pill status-pill-danger">❌ Pelanggaran</span>';

        // Worker Snapshot Crop
        let snapshotHtml = '<div style="width:48px; height:48px; background:#182033; border-radius:6px; display:flex; align-items:center; justify-content:center; color:#64748b; font-size:0.75rem;">N/A</div>';
        if (rec.snapshot_filename) {
          const imgUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/reports/snapshots/${rec.snapshot_filename}`;
          snapshotHtml = `
            <img src="${imgUrl}" class="worker-thumb" alt="Pekerja #${rec.track_id}"
                 title="Klik untuk melihat bukti foto snapshot"
                 data-full="${imgUrl}"
                 data-caption="Pekerja #${rec.track_id} - ${rec.date_str} ${rec.time_str} (${isComplete ? 'LOLOS' : 'PELANGGARAN'})"
            />
          `;
        }

        // APD Badges
        const helmBadge = rec.helm_detected 
          ? '<span class="apd-mini-badge apd-mini-ok">🪖 Helm ✓</span>' 
          : '<span class="apd-mini-badge apd-mini-bad">🪖 Helm ✗</span>';
        const rompiBadge = rec.rompi_valid 
          ? `<span class="apd-mini-badge apd-mini-ok">🦺 Rompi (${rec.rompi_color || 'Ok'}) ✓</span>` 
          : '<span class="apd-mini-badge apd-mini-bad">🦺 Rompi ✗</span>';
        const celanaBadge = rec.celana_detected 
          ? '<span class="apd-mini-badge apd-mini-ok">👖 Celana ✓</span>' 
          : '<span class="apd-mini-badge apd-mini-bad">👖 Celana ✗</span>';
        const sepatuBadge = rec.sepatu_closed 
          ? '<span class="apd-mini-badge apd-mini-ok">👞 Sepatu ✓</span>' 
          : '<span class="apd-mini-badge apd-mini-bad">👞 Sepatu ✗</span>';

        const sourceIcon = (rec.inference_source || '').includes('GEMINI') ? '🌐 Gemini VLM' : '⚡ GPU Lokal';
        const notesText = rec.missing_items && rec.missing_items.length > 0 
          ? `<span style="color:var(--accent-red); font-weight:500;">Kurang: ${rec.missing_items.join(', ')}</span>`
          : `<span style="color:var(--accent-green); font-weight:500;">Kepatuhan 100% K3</span>`;

        return `
          <tr>
            <td>${snapshotHtml}</td>
            <td style="font-family:var(--font-mono); font-size:0.8rem;">
              <div>${rec.date_str}</div>
              <div style="color:var(--text-muted); font-size:0.75rem;">${rec.time_str}</div>
            </td>
            <td>
              <strong style="color:var(--text-primary); font-weight:600;">Subjek #${rec.track_id}</strong>
            </td>
            <td>${statusBadge}</td>
            <td>
              <div style="display:flex; flex-direction:column; gap:3px;">
                <div>${helmBadge} ${rompiBadge}</div>
                <div>${celanaBadge} ${sepatuBadge}</div>
              </div>
            </td>
            <td style="font-family:var(--font-mono); font-size:0.75rem; color:var(--text-secondary);">
              <div>${sourceIcon}</div>
              <div style="color:var(--text-muted);">${rec.inference_time_ms} ms</div>
            </td>
            <td style="font-size:0.82rem;">
              ${notesText}
            </td>
          </tr>
        `;
      }).join('');

      // Attach Click Listeners to Snapshot Thumbnails
      const thumbs = reportsTableBody.querySelectorAll('.worker-thumb');
      thumbs.forEach(thumb => {
        thumb.addEventListener('click', () => {
          if (snapshotImg && snapshotCaption && modalSnapshot) {
            snapshotImg.src = thumb.getAttribute('data-full');
            snapshotCaption.textContent = thumb.getAttribute('data-caption');
            modalSnapshot.style.display = 'flex';
          }
        });
      });

    } catch (e) {
      console.error('Error fetching reports:', e);
      reportsTableBody.innerHTML = `
        <tr>
          <td colspan="7" style="text-align:center; padding:2rem; color:var(--accent-red);">
            Gagal memuat data laporan: ${e}
          </td>
        </tr>
      `;
    }
  }

  // Close Snapshot Modal
  if (btnCloseSnapshot && modalSnapshot) {
    btnCloseSnapshot.addEventListener('click', () => {
      modalSnapshot.style.display = 'none';
    });
    modalSnapshot.addEventListener('click', (e) => {
      if (e.target === modalSnapshot) {
        modalSnapshot.style.display = 'none';
      }
    });
  }

  // --- 7. PENGATURAN (SETTINGS) CONTROLLER ---

  // Hardware Light Test Function
  async function triggerLightTest(action) {
    try {
      const res = await fetch(iotTestUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      });
      const data = await res.json();
      console.log(`[IoT Test] Action: ${action}, Result:`, data);
    } catch (e) {
      alert(`Gagal mengirim sinyal tes hardware ke server: ${e}`);
    }
  }

  if (btnTestGreen) btnTestGreen.addEventListener('click', () => triggerLightTest('green'));
  if (btnTestRed) btnTestRed.addEventListener('click', () => triggerLightTest('red'));
  if (btnTestOff) btnTestOff.addEventListener('click', () => triggerLightTest('off'));

  // Test Cloud Gemini API Latency
  if (btnPingGemini) {
    btnPingGemini.addEventListener('click', async () => {
      try {
        btnPingGemini.disabled = true;
        btnPingGemini.textContent = '⏳ Menguji...';
        const res = await fetch(pingUrl, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'ONLINE') {
          alert(`✅ Google Gemini API Cloud Terhubung!\nLatensi: ${data.latency_ms} ms\nStatus: ONLINE`);
        } else {
          alert(`⚠️ Hasil Ping API:\nStatus: ${data.status}\nLatensi: ${data.latency_ms} ms\nPesan: ${data.message || data.reply || '-'}`);
        }
      } catch (e) {
        alert(`❌ Gagal menghubungi endpoint ping: ${e}`);
      } finally {
        btnPingGemini.disabled = false;
        btnPingGemini.textContent = '📡 Uji Latensi API';
      }
    });
  }

  // Save Settings (API Key & Preferences)
  if (btnSaveSettings) {
    btnSaveSettings.addEventListener('click', async () => {
      const key = inputGeminiKey ? inputGeminiKey.value.trim() : '';
      if (!key) {
        alert('Pengaturan umum tersimpan. (Masukkan API key jika ingin memperbarui kunci Gemini)');
        return;
      }
      try {
        btnSaveSettings.disabled = true;
        btnSaveSettings.textContent = 'Menyimpan...';
        const res = await fetch(configKeyUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ api_key: key })
        });
        const data = await res.json();
        if (data.status === 'success') {
          alert('✅ Google Gemini API Key berhasil disimpan di server! Cloud VLM aktif.');
          if (inputGeminiKey) inputGeminiKey.value = '';
        } else {
          alert('❌ Gagal menyimpan API Key: ' + data.message);
        }
      } catch (err) {
        alert('❌ Koneksi ke backend gagal: ' + err);
      } finally {
        btnSaveSettings.disabled = false;
        btnSaveSettings.textContent = '💾 Simpan Pengaturan';
      }
    });
  }

});
