/**
 * DEPRO - Main Controller
 * Handles SPA 3-Tab navigation (Monitoring, Laporan, Pengaturan),
 * real-time telemetry, video toolbar controls, integrated report auditing,
 * and IoT hardware / AI settings.
 */

import { TelemetryWebSocket } from './websocket.js';
import { HUDOverlay } from './hud_overlay.js';
import { APDVisualizer } from './apd_card.js';
import { loadCatalog, replaceCatalog, activeItems, assessItem } from './ppe_catalog.js';

/** Meloloskan teks untuk disisipkan ke dalam template HTML. */
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text == null ? '' : String(text);
  return div.innerHTML.replace(/"/g, '&quot;');
}

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
  const dotVlm = document.getElementById('dot-vlm');
  const vlmDownBanner = document.getElementById('vlm-down-banner');
  const vlmDownText = document.getElementById('vlm-down-text');
  const fpsText = document.getElementById('fps-counter');

  // Video Viewport & Canvas
  const canvasElement = document.getElementById('hud-canvas');
  const liveVideoImg = document.getElementById('live-stream');

  // Video Toolbar Controls
  const toggleCorridorGuide = document.getElementById('toggle-corridor-guide');
  const toggleAudioMute = document.getElementById('toggle-audio-mute');
  const audioSwitchLabel = document.getElementById('audio-switch-label');
  const btnToggleTechDetails = document.getElementById('btn-toggle-tech-details');
  const techDetailsDrawer = document.getElementById('tech-details-drawer');
  const techChevron = document.getElementById('tech-chevron');
  const btnResetInspection = document.getElementById('btn-reset-inspection');

  // Technical Drawer Fields
  // Hanya engine mode yang diurus di sini; field teknis lain milik APDVisualizer.
  const techEngineMode = document.getElementById('tech-engine-mode');

  // Reports View Elements
  const kpiTotal = document.getElementById('kpi-total');
  const kpiComplete = document.getElementById('kpi-complete');
  const kpiViolations = document.getElementById('kpi-violations');
  const kpiRate = document.getElementById('kpi-rate');
  const kpiBackup = document.getElementById('kpi-backup');
  const kpiOutages = document.getElementById('kpi-outages');
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

  // Camera Source Elements
  const cameraSelectHeader = document.getElementById('camera-select');
  const cameraSelectSettings = document.getElementById('setting-camera-index');
  const btnScanCameras = document.getElementById('btn-scan-cameras');
  const cameraScanStatus = document.getElementById('camera-scan-status');
  const cameraActiveInfo = document.getElementById('camera-active-info');
  const cameraQualityNote = document.getElementById('camera-quality-note');
  const settingCorridorFilter = document.getElementById('setting-corridor-filter');
  const ppeRuleList = document.getElementById('ppe-rule-list');
  const ppeRuleStatus = document.getElementById('ppe-rule-status');
  const btnReleaseCamera = document.getElementById('btn-release-camera');

  // Dialog Pemilihan Sumber Kamera
  const pickerModal = document.getElementById('camera-picker-modal');
  const pickerList = document.getElementById('camera-picker-list');
  const pickerStatus = document.getElementById('camera-picker-status');
  const btnPickerScan = document.getElementById('btn-picker-scan');
  const btnPickerConfirm = document.getElementById('btn-picker-confirm');

  // Settings View Elements
  const btnTestGreen = document.getElementById('btn-test-green');
  const btnTestRed = document.getElementById('btn-test-red');
  const btnTestOff = document.getElementById('btn-test-off');
  const inputVlmKey = document.getElementById('input-vlm-key');
  const inputAdminToken = document.getElementById('input-admin-token');
  const btnPingVlm = document.getElementById('btn-ping-vlm');
  const vlmProviderInfo = document.getElementById('vlm-provider-info');
  const vlmBackupInfo = document.getElementById('vlm-backup-info');
  const vlmKeyRow = document.getElementById('vlm-key-row');
  const labelVlmKey = document.getElementById('label-vlm-key');
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
  const ppeRulesUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/ppe-rules`;
  const ppeRulesActiveUrl = `${ppeRulesUrl}/active`;
  const resetUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/reset`;
  const configKeyUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/config/vlm-key`;
  const vlmConfigUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/config/vlm`;
  const reportsUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/reports`;
  const exportCsvUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/reports/export`;
  const pingUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/monitoring/ping`;
  const iotTestUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/iot/test`;
  const audioConfigUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/config/audio`;
  const camerasUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/cameras`;
  const cameraScanUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/cameras/scan`;
  const cameraConfigUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/config/camera`;
  const corridorConfigUrl = `${httpProtocol}//${backendHost}${portSuffix}/api/config/corridor`;

  // --- ADMIN TOKEN (opsional) ---
  // Hanya relevan kalau server dijalankan dengan ADMIN_TOKEN. Disimpan di
  // browser ini saja dan dilampirkan pada perintah yang mengubah state server.
  const ADMIN_TOKEN_STORAGE_KEY = 'safeguard_admin_token';

  function getAdminToken() {
    try {
      return localStorage.getItem(ADMIN_TOKEN_STORAGE_KEY) || '';
    } catch (e) {
      return '';
    }
  }

  function jsonHeaders() {
    const headers = { 'Content-Type': 'application/json' };
    const token = getAdminToken();
    if (token) headers['X-Admin-Token'] = token;
    return headers;
  }

  function authHeaders() {
    const token = getAdminToken();
    return token ? { 'X-Admin-Token': token } : {};
  }

  if (inputAdminToken) {
    inputAdminToken.value = getAdminToken();
  }

  // Active Controller State
  let wsConnected = false;
  let currentStatusFilter = 'all';
  let currentDateFilter = '';

  // Initialize live video stream source
  if (liveVideoImg) {
    liveVideoImg.src = streamUrl;
  }

  // Initialize Canvas HUD and Visualizer
  const hud = new HUDOverlay(canvasElement);
  const visualizer = new APDVisualizer();

  // Checklist baru bisa digambar setelah katalog APD dari backend tiba
  loadCatalog(ppeRulesUrl)
    .then((items) => {
      visualizer.setCatalog(activeItems(items));
      renderPpeRuleSettings(items);
    })
    .catch((err) => console.error('[Katalog APD] Gagal memuat /api/ppe-rules:', err));

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
          headers: jsonHeaders(),
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
        await fetch(resetUrl, { method: 'POST', headers: authHeaders() });
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

      // 0b. Status kamera sebenarnya (bukan status WebSocket)
      if (telemetry.camera) {
        updateCameraRibbon(telemetry.camera);
        if (telemetry.camera.status === 'IDLE') {
          showPicker();
        } else if (pickerVisible && telemetry.camera.status === 'OK') {
          hidePicker();
        }
      }

      // 1. Update FPS Display
      if (fpsText && telemetry.fps !== undefined) {
        fpsText.textContent = `${Number(telemetry.fps).toFixed(1).replace('.', ',')} FPS`;
      }

      // 2. Status VLM (utama / cadangan / gangguan)
      if (telemetry.api_monitor) {
        updateRibbonCloudUI(telemetry.api_monitor, telemetry.vlm);
      }

      // 3. Technical Drawer, badge subjek, dan checklist APD seluruhnya diurus
      //    APDVisualizer.update() di langkah 5 — satu-satunya tempat yang membaca
      //    bentuk payload `active_track` yang benar dari backend.

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
      wsConnected = status === 'connected';
      if (!wsConnected && dotCamera && ribbonCameraText) {
        dotCamera.className = 'status-dot red';
        ribbonCameraText.textContent = 'Server terputus';
      }
    }
  );

  // Ribbon kamera mencerminkan kondisi perangkat, bukan koneksi WebSocket —
  // dulu keduanya tertukar sehingga tertulis "Kamera aktif" saat kamera dicabut.
  function updateCameraRibbon(camera) {
    if (!dotCamera || !ribbonCameraText || !wsConnected) return;

    const name = camera.name || `Kamera ${camera.index}`;
    switch (camera.status) {
      case 'OK':
        dotCamera.className = 'status-dot green';
        ribbonCameraText.textContent = `${name} — ${camera.width}×${camera.height}`;
        break;
      case 'OPENING':
        dotCamera.className = 'status-dot amber';
        ribbonCameraText.textContent = `Membuka ${name}...`;
        break;
      case 'IDLE':
        dotCamera.className = 'status-dot amber';
        ribbonCameraText.textContent = 'Kamera belum dipilih';
        break;
      case 'OPTIMIZING':
        dotCamera.className = 'status-dot amber';
        ribbonCameraText.textContent = `Mengukur mode terbaik ${name}...`;
        break;
      case 'LOST':
        dotCamera.className = 'status-dot red';
        ribbonCameraText.textContent = 'Kamera terputus — menyambung ulang';
        break;
      default:
        dotCamera.className = 'status-dot amber';
        ribbonCameraText.textContent = 'Tidak ada kamera (mode simulasi)';
    }
  }

  // Status VLM di pita atas: 🟢 utama, 🟡 cadangan otomatis, 🔴 gangguan (T27).
  // Tidak ada sakelar: peralihan ke cadangan terjadi otomatis di backend.
  function describeEngine(engine, info) {
    if (!info) return 'VLM';
    const where = info.is_local ? 'lokal' : 'cloud';
    const latency = engine && engine.latency_ms ? ` ${Math.round(engine.latency_ms)} ms` : '';
    return `${info.provider} ${where}${latency}`;
  }

  function updateRibbonCloudUI(monitor, vlm) {
    if (!ribbonCloudText) return;
    const backupInfo = vlm ? vlm.backup : null;
    let dot = 'amber';
    let text;

    if (monitor.mode === 'UTAMA') {
      dot = 'green';
      text = `VLM utama: ${describeEngine(monitor.primary, vlm)}`;
    } else if (monitor.mode === 'CADANGAN') {
      dot = 'amber';
      const why = !(monitor.primary && monitor.primary.configured) ? 'utama nonaktif'
        : monitor.primary_down ? 'utama terputus' : 'utama gagal';
      text = `VLM cadangan (${why}): ${describeEngine(monitor.backup, backupInfo)}`;
    } else {
      dot = 'red';
      text = 'VLM gangguan: utama & cadangan tidak menjawab';
    }
    if (dotVlm) dotVlm.className = `status-dot ${dot}`;
    ribbonCloudText.textContent = text;
    if (techEngineMode) techEngineMode.textContent = monitor.mode;

    // Spanduk hanya saat benar-benar tidak ada VLM yang bisa memutuskan
    if (vlmDownBanner) {
      const down = monitor.mode === 'GANGGUAN';
      vlmDownBanner.hidden = !down;
      if (down && vlmDownText) {
        const reason = monitor.last_no_decision_reason ? ` (${monitor.last_no_decision_reason})` : '';
        vlmDownText.textContent =
          `VLM utama & cadangan tidak menjawab${reason}. Pekerja diminta menunggu, pemeriksaan diulang otomatis.`;
      }
    }
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
      if (kpiBackup) kpiBackup.textContent = data.backup_count || 0;
      if (kpiOutages) kpiOutages.textContent = data.system_outages || 0;

      const records = data.page_records || [];
      const catalog = await loadCatalog(ppeRulesUrl);
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
            <img src="${imgUrl}" class="worker-thumb thumb-preview-img" alt="Pekerja #${rec.track_id}"
                 title="Klik untuk melihat bukti foto snapshot"
                 data-full="${imgUrl}"
                 data-caption="Pekerja #${rec.track_id} - ${rec.date_str} ${rec.time_str} (${isComplete ? 'LOLOS' : 'PELANGGARAN'})"
            />
          `;
        }

        // APD Badges: hanya item yang dinilai pada inspeksi ini. Item yang saat
        // itu dimatikan operator tidak ada di `rec.items` dan tidak ditampilkan.
        const recItems = rec.items || {};
        const apdBadges = catalog.filter((item) => item.key in recItems).map((item) => {
          const { ok, text } = assessItem(item, recItems[item.key]);
          const name = escapeHtml(item.short_label);
          const detail = ok && item.reports_color && text !== item.ok_label ? ` (${escapeHtml(text)})` : '';
          return ok
            ? `<span class="apd-mini-badge apd-mini-ok">${item.icon} ${name}${detail} ✓</span>`
            : `<span class="apd-mini-badge apd-mini-bad" title="${escapeHtml(text)}">${item.icon} ${name} ✗</span>`;
        });

        const source = rec.inference_source || '';
        // VLM_LIVE:<penyedia>/<model> = utama, VLM_CADANGAN:... = cadangan (T27).
        // Label lama tetap terbaca: GEMINI_LIVE (sebelum T23), VLM_GAGAL (T21-T26),
        // dan LOCAL_*/OFFLINE_FALLBACK dari heuristik OpenCV yang sudah dibuang.
        const sourceIcon = source.startsWith('VLM_GAGAL') ? '⚠️ VLM gagal (ditolak)'
          : source.startsWith('VLM_LIVE:') ? `🌐 ${escapeHtml(source.slice('VLM_LIVE:'.length))}`
          : source.startsWith('VLM_CADANGAN:') ? `🛟 Cadangan: ${escapeHtml(source.slice('VLM_CADANGAN:'.length))}`
          : source.includes('GEMINI') ? '🌐 Gemini VLM' : '⚡ Heuristik lokal (lama)';
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
              <div style="display:flex; flex-wrap:wrap; gap:3px;">
                ${apdBadges.join(' ')}
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

  // --- 6b. SUMBER KAMERA (USB / WEBCAM BAWAAN) ---

  let cameraScanPoll = null;

  function modeLabel(mode) {
    if (!mode) return 'mode belum diketahui';
    const fps = mode.fps ? ` @${Math.round(mode.fps)} FPS` : '';
    return `${mode.width}×${mode.height}${fps}`;
  }

  function fillCameraSelect(selectEl, devices, activeIndex) {
    if (!selectEl) return;
    selectEl.innerHTML = '';

    if (!devices.length) {
      selectEl.innerHTML = '<option value="">Tidak ada kamera terdeteksi</option>';
      return;
    }

    devices.forEach((dev) => {
      const opt = document.createElement('option');
      opt.value = String(dev.index);
      // Nama asli perangkat penting: indeks saja menyesatkan, misalnya indeks 1
      // bisa berupa kamera virtual, bukan kamera fisik kedua.
      let label = dev.name || `Kamera ${dev.index}`;
      if (dev.selected_mode) {
        label += ` — ${modeLabel(dev.selected_mode)}`;
      } else if (dev.scanned === false) {
        // Belum diukur bukan berarti bermasalah — kamera USB yang baru dicolok
        // tetap bisa dipilih tanpa harus memindai lebih dulu.
        label += ' — belum dipindai';
      } else if (!dev.available) {
        label += ' — tidak tersedia';
      }
      opt.textContent = label;
      opt.disabled = dev.scanned !== false && !dev.available && dev.index !== activeIndex;
      if (dev.index === activeIndex) opt.selected = true;
      selectEl.appendChild(opt);
    });
  }

  async function loadCameras() {
    try {
      const res = await fetch(camerasUrl);
      const data = await res.json();
      const devices = data.devices || [];
      const active = data.active || {};

      fillCameraSelect(cameraSelectHeader, devices, active.index);
      fillCameraSelect(cameraSelectSettings, devices, active.index);

      if (cameraActiveInfo) {
        cameraActiveInfo.textContent = active.name
          ? `Aktif: ${active.name} — ${active.width}×${active.height} (${active.status})`
          : '—';
      }

      if (cameraQualityNote) {
        if (data.quality_warning) {
          cameraQualityNote.style.display = '';
          cameraQualityNote.textContent =
            '⚠️ Resolusi kamera rendah. Video lebih lancar, tetapi potongan gambar yang '
            + 'dikirim ke AI lebih kecil sehingga penilaian helm dan sepatu bisa kurang teliti.';
        } else {
          cameraQualityNote.style.display = 'none';
        }
      }

      if (cameraScanStatus && data.last_scan_time && data.last_scan_time !== '-') {
        cameraScanStatus.textContent = data.scanning
          ? '⏳ Memindai kamera...'
          : `Pemindaian terakhir pukul ${data.last_scan_time}.`;
      }

      return data;
    } catch (e) {
      console.error('Gagal memuat daftar kamera:', e);
      return null;
    }
  }

  async function switchCamera(index) {
    if (index === '' || index === null || index === undefined) return;
    try {
      const res = await fetch(cameraConfigUrl, {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify({ index: Number(index) })
      });
      const data = await res.json();
      if (!res.ok) {
        alert(`Gagal berpindah kamera: ${data.message || res.status}`);
        return;
      }
      // Pergantian dikerjakan di sisi server; aliran MJPEG dimuat ulang setelah
      // kamera baru sempat terbuka, dengan pembeda cache agar benar-benar segar.
      setTimeout(() => {
        if (liveVideoImg) liveVideoImg.src = `${streamUrl}?t=${Date.now()}`;
        loadCameras();
      }, 2500);
    } catch (e) {
      alert(`Gagal mengirim permintaan pindah kamera: ${e}`);
    }
  }

  if (cameraSelectHeader) {
    cameraSelectHeader.addEventListener('change', (e) => switchCamera(e.target.value));
  }
  if (cameraSelectSettings) {
    cameraSelectSettings.addEventListener('change', (e) => switchCamera(e.target.value));
  }

  if (btnScanCameras) {
    btnScanCameras.addEventListener('click', async () => {
      try {
        btnScanCameras.disabled = true;
        btnScanCameras.textContent = '⏳ Memindai...';
        if (cameraScanStatus) cameraScanStatus.textContent = 'Mengukur kemampuan setiap kamera...';

        await fetch(cameraScanUrl, { method: 'POST', headers: authHeaders() });

        // Probing berjalan di latar server, jadi hasilnya ditunggu dengan polling
        if (cameraScanPoll) clearInterval(cameraScanPoll);
        cameraScanPoll = setInterval(async () => {
          const data = await loadCameras();
          if (data && !data.scanning) {
            clearInterval(cameraScanPoll);
            cameraScanPoll = null;
            btnScanCameras.disabled = false;
            btnScanCameras.textContent = '🔄 Pindai kamera';
          }
        }, 1500);
      } catch (e) {
        btnScanCameras.disabled = false;
        btnScanCameras.textContent = '🔄 Pindai kamera';
        alert(`Gagal memulai pemindaian kamera: ${e}`);
      }
    });
  }

  // Sakelar Virtual Inspection Corridor
  if (settingCorridorFilter) {
    settingCorridorFilter.addEventListener('change', async (e) => {
      try {
        await fetch(corridorConfigUrl, {
          method: 'POST',
          headers: jsonHeaders(),
          body: JSON.stringify({ enabled: e.target.checked })
        });
      } catch (err) {
        console.error('Gagal mengubah pengaturan koridor:', err);
      }
    });
  }

  // Aturan APD Wajib: satu sakelar per item katalog
  function renderPpeRuleSettings(items) {
    if (!ppeRuleList) return;
    ppeRuleList.innerHTML = '';

    items.forEach((item) => {
      const label = document.createElement('label');
      label.className = 'form-checkbox-label';

      const input = document.createElement('input');
      input.type = 'checkbox';
      input.checked = item.required;
      input.dataset.key = item.key;
      input.addEventListener('change', () => setPpeItemActive(input));

      const text = document.createElement('span');
      text.textContent = `${item.icon} ${item.label}`;
      label.append(input, text);
      ppeRuleList.appendChild(label);
    });
  }

  async function setPpeItemActive(input) {
    const key = input.dataset.key;
    const wanted = input.checked;
    ppeRuleList.querySelectorAll('input').forEach((el) => { el.disabled = true; });
    ppeRuleStatus.textContent = 'Menyimpan...';

    try {
      const res = await fetch(ppeRulesActiveUrl, {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify({ active: { [key]: wanted } })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);

      replaceCatalog(data.items);
      visualizer.setCatalog(activeItems(data.items));
      renderPpeRuleSettings(data.items);
      ppeRuleStatus.textContent = 'Tersimpan. Berlaku untuk inspeksi berikutnya.';
    } catch (err) {
      input.checked = !wanted;
      ppeRuleStatus.textContent = `Gagal menyimpan: ${err.message}`;
    } finally {
      ppeRuleList.querySelectorAll('input').forEach((el) => { el.disabled = false; });
    }
  }

  // --- 6c. DIALOG PEMILIHAN SUMBER KAMERA ---
  // Server sengaja tidak membuka kamera apa pun saat menyala, supaya tidak ada
  // perangkat yang terlanjur dipakai lalu diganti. Operator memilih lebih dulu.

  let pickerVisible = false;
  let pickerChoice = null;
  let pickerPoll = null;

  function renderPickerList(devices, savedName) {
    if (!pickerList) return;

    if (!devices.length) {
      pickerList.innerHTML = '<p class="form-help">Tidak ada kamera terdeteksi. '
        + 'Colokkan kamera lalu tekan Pindai kemampuan.</p>';
      if (btnPickerConfirm) btnPickerConfirm.disabled = true;
      return;
    }

    // Kamera yang terakhir dipakai hanya disorot sebagai bawaan; video tetap
    // tidak tersambung sebelum tombolnya ditekan.
    if (pickerChoice === null) {
      const saved = devices.find(function (d) { return savedName && d.name === savedName; });
      pickerChoice = saved ? saved.index : devices[0].index;
    }

    pickerList.innerHTML = '';
    devices.forEach(function (dev) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'camera-picker-item' + (dev.index === pickerChoice ? ' selected' : '');

      const meta = dev.selected_mode
        ? modeLabel(dev.selected_mode)
        : (dev.scanned === false ? 'belum dipindai' : 'tidak tersedia');
      const tanda = (savedName && dev.name === savedName) ? '  -  terakhir dipakai' : '';

      const elName = document.createElement('span');
      elName.className = 'picker-name';
      elName.textContent = dev.name;

      const elMeta = document.createElement('span');
      elMeta.className = 'picker-meta';
      elMeta.textContent = 'index ' + dev.index + '  -  ' + meta + tanda;

      btn.appendChild(elName);
      btn.appendChild(elMeta);
      btn.addEventListener('click', function () {
        pickerChoice = dev.index;
        renderPickerList(devices, savedName);
      });
      pickerList.appendChild(btn);
    });

    if (btnPickerConfirm) btnPickerConfirm.disabled = false;
  }

  async function refreshPicker() {
    try {
      const res = await fetch(camerasUrl);
      const data = await res.json();
      renderPickerList(data.devices || [], data.saved ? data.saved.name : null);
      if (pickerStatus) {
        if (data.scanning) {
          pickerStatus.textContent = 'Mengukur kemampuan kamera...';
        } else if (data.last_scan_time && data.last_scan_time !== '-') {
          pickerStatus.textContent = 'Pemindaian terakhir pukul ' + data.last_scan_time + '.';
        } else {
          pickerStatus.textContent = 'Pemindaian bersifat opsional; kamera tetap bisa langsung dipakai.';
        }
      }
      return data;
    } catch (e) {
      if (pickerStatus) pickerStatus.textContent = 'Gagal memuat daftar kamera: ' + e;
      return null;
    }
  }

  function showPicker() {
    if (pickerVisible || !pickerModal) return;
    pickerVisible = true;
    pickerChoice = null;
    pickerModal.style.display = 'flex';
    refreshPicker();
  }

  function hidePicker() {
    if (!pickerModal) return;
    pickerVisible = false;
    pickerModal.style.display = 'none';
  }

  if (btnPickerConfirm) {
    btnPickerConfirm.addEventListener('click', async function () {
      if (pickerChoice === null) return;
      btnPickerConfirm.disabled = true;
      btnPickerConfirm.textContent = 'Menyambungkan...';
      if (pickerStatus) pickerStatus.textContent = 'Membuka kamera...';

      try {
        await fetch(cameraConfigUrl, {
          method: 'POST',
          headers: jsonHeaders(),
          body: JSON.stringify({ index: pickerChoice })
        });

        // Pembukaan kamera dikerjakan thread pembaca di server, jadi hasilnya
        // ditunggu lewat polling sebelum dialog ditutup.
        if (pickerPoll) clearInterval(pickerPoll);
        let tries = 0;
        pickerPoll = setInterval(async function () {
          tries += 1;
          const data = await refreshPicker();
          const st = (data && data.active) ? data.active.status : null;
          if (st === 'OK' || st === 'SYNTHETIC' || tries > 25) {
            clearInterval(pickerPoll);
            pickerPoll = null;
            btnPickerConfirm.disabled = false;
            btnPickerConfirm.textContent = 'Gunakan kamera ini';
            if (st === 'SYNTHETIC') {
              if (pickerStatus) {
                pickerStatus.textContent = 'Kamera itu tidak dapat dibuka. Pilih sumber lain.';
              }
              return;
            }
            hidePicker();
            if (liveVideoImg) liveVideoImg.src = streamUrl + '?t=' + Date.now();
            loadCameras();
          }
        }, 1000);
      } catch (e) {
        btnPickerConfirm.disabled = false;
        btnPickerConfirm.textContent = 'Gunakan kamera ini';
        if (pickerStatus) pickerStatus.textContent = 'Gagal menyambungkan: ' + e;
      }
    });
  }

  if (btnPickerScan) {
    btnPickerScan.addEventListener('click', async function () {
      btnPickerScan.disabled = true;
      btnPickerScan.textContent = 'Memindai...';
      try {
        await fetch(cameraScanUrl, { method: 'POST', headers: authHeaders() });
        const iv = setInterval(async function () {
          const data = await refreshPicker();
          if (data && !data.scanning) {
            clearInterval(iv);
            btnPickerScan.disabled = false;
            btnPickerScan.textContent = 'Pindai kemampuan';
          }
        }, 1500);
      } catch (e) {
        btnPickerScan.disabled = false;
        btnPickerScan.textContent = 'Pindai kemampuan';
      }
    });
  }

  // Lepas kamera dan kembali ke dialog pemilihan
  if (btnReleaseCamera) {
    btnReleaseCamera.addEventListener('click', async function () {
      try {
        await fetch(cameraConfigUrl, {
          method: 'POST',
          headers: jsonHeaders(),
          body: JSON.stringify({ index: null })
        });
      } catch (e) {
        alert('Gagal melepas kamera: ' + e);
      }
    });
  }

  loadCameras();

  // --- 7. PENGATURAN (SETTINGS) CONTROLLER ---

  // Hardware Light Test Function
  async function triggerLightTest(action) {
    try {
      const res = await fetch(iotTestUrl, {
        method: 'POST',
        headers: jsonHeaders(),
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

  // Penyedia VLM aktif untuk tab Pengaturan (API key tidak pernah dikirim ke browser)
  async function refreshVlmInfo() {
    try {
      const res = await fetch(vlmConfigUrl);
      const vlm = await res.json();
      const describe = (e) => {
        const status = e.is_live ? '✅ aktif' : (e.needs_key && !e.has_key ? '⚠️ API key belum disetel' : `⚠️ tidak aktif${e.error ? ` (${e.error})` : ''}`);
        return `${e.provider} · ${e.model || '(model belum disetel)'} · ${e.is_local ? 'lokal' : 'cloud'} · batas ${e.timeout_s} dtk · ${status}`;
      };
      if (vlmProviderInfo) vlmProviderInfo.textContent = describe(vlm);
      if (vlmBackupInfo) {
        vlmBackupInfo.textContent = vlm.backup ? describe(vlm.backup) : '— tidak ada (VLM_BACKUP_PROVIDER=none)';
      }
      // Model lokal (Ollama/vLLM) tidak memakai API key
      if (vlmKeyRow) vlmKeyRow.style.display = vlm.needs_key ? '' : 'none';
      if (labelVlmKey) labelVlmKey.textContent = `API Key ${vlm.provider} (Server-Side)`;
    } catch (e) {
      if (vlmProviderInfo) vlmProviderInfo.textContent = 'Tidak dapat memuat info penyedia VLM';
    }
  }
  refreshVlmInfo();

  // Uji latensi ke penyedia VLM aktif
  if (btnPingVlm) {
    btnPingVlm.addEventListener('click', async () => {
      try {
        btnPingVlm.disabled = true;
        btnPingVlm.textContent = '⏳ Menguji...';
        const res = await fetch(pingUrl, { method: 'POST', headers: authHeaders() });
        const data = await res.json();
        // Hasil per VLM: utama dan cadangan diuji terpisah
        const icon = data.status === 'ONLINE' ? '✅' : '⚠️';
        alert(`${icon} Uji latensi VLM\n${(data.message || '-').split('; ').join('\n')}`);
      } catch (e) {
        alert(`❌ Gagal menghubungi endpoint ping: ${e}`);
      } finally {
        btnPingVlm.disabled = false;
        btnPingVlm.textContent = '📡 Uji Latensi API';
      }
    });
  }

  // Save Settings (API Key & Preferences)
  if (btnSaveSettings) {
    btnSaveSettings.addEventListener('click', async () => {
      // Token admin disimpan lokal di browser, tidak pernah dikirim ke server
      // kecuali sebagai header pada perintah yang mengubah state.
      if (inputAdminToken) {
        try {
          const token = inputAdminToken.value.trim();
          if (token) {
            localStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, token);
          } else {
            localStorage.removeItem(ADMIN_TOKEN_STORAGE_KEY);
          }
        } catch (e) {
          console.warn('Tidak dapat menyimpan token admin di browser ini:', e);
        }
      }

      const key = inputVlmKey ? inputVlmKey.value.trim() : '';
      if (!key) {
        alert('Pengaturan tersimpan. (Masukkan API key jika ingin memperbarui kunci penyedia VLM)');
        return;
      }
      try {
        btnSaveSettings.disabled = true;
        btnSaveSettings.textContent = 'Menyimpan...';
        const res = await fetch(configKeyUrl, {
          method: 'POST',
          headers: jsonHeaders(),
          body: JSON.stringify({ api_key: key })
        });
        const data = await res.json();
        if (data.status === 'success') {
          alert(`✅ API key ${data.provider} tersimpan di server. VLM ${data.is_live ? 'aktif' : 'belum aktif'}.`);
          if (inputVlmKey) inputVlmKey.value = '';
          refreshVlmInfo();
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
