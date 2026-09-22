/**
 * SAFEGUARD AI - Main Controller
 */

import { TelemetryWebSocket } from './websocket.js';
import { HUDOverlay } from './hud_overlay.js';
import { APDVisualizer } from './apd_card.js';

document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const wsStatusBadge = document.getElementById('ws-status-badge');
  const wsStatusDot = document.getElementById('ws-status-dot');
  const wsStatusText = document.getElementById('ws-status-text');
  const fpsText = document.getElementById('fps-counter');
  const vlmModeBadge = document.getElementById('vlm-mode-badge');
  const canvasElement = document.getElementById('hud-canvas');
  const liveVideoImg = document.getElementById('live-stream');

  const btnReset = document.getElementById('btn-reset');
  const btnSettings = document.getElementById('btn-settings');
  const modalSettings = document.getElementById('settings-modal');
  const btnCloseModal = document.getElementById('btn-close-modal');
  const btnSaveKey = document.getElementById('btn-save-key');
  const inputApiKey = document.getElementById('input-gemini-key');

  // Determine backend URL
  const backendHost = window.location.hostname || 'localhost';
  const backendPort = window.location.port || '8000';
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const httpProtocol = window.location.protocol === 'https:' ? 'https:' : 'http:';

  const wsUrl = `${wsProtocol}//${backendHost}:${backendPort}/ws`;
  const streamUrl = `${httpProtocol}//${backendHost}:${backendPort}/api/stream`;
  const resetUrl = `${httpProtocol}//${backendHost}:${backendPort}/api/reset`;
  const configKeyUrl = `${httpProtocol}//${backendHost}:${backendPort}/api/config/gemini-key`;

  // Set stream src
  liveVideoImg.src = streamUrl;

  // Initialize components
  const hud = new HUDOverlay(canvasElement);
  const visualizer = new APDVisualizer();

  // WebSocket Telemetry Listener
  const ws = new TelemetryWebSocket(
    wsUrl,
    (telemetry) => {
      // 1. Update FPS
      if (telemetry.fps !== undefined) {
        fpsText.textContent = `${telemetry.fps} FPS`;
      }

      // 2. Update Engine Mode Badge
      if (telemetry.is_live_gemini) {
        vlmModeBadge.textContent = 'HYBRID: GEMINI + GPU';
        vlmModeBadge.style.color = 'var(--color-green)';
      } else {
        vlmModeBadge.textContent = '⚡ FAST-PASS (LOKAL GPU)';
        vlmModeBadge.style.color = 'var(--color-blue)';
      }


      // 3. Render Canvas HUD with corridor guides
      if (telemetry.corridor) {
        hud.setCorridor(telemetry.corridor);
      }
      hud.setDetections(telemetry.detections);

      // 4. Update APD Visualizer (Cards, Tower Light, Hero Banner, Log)
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

  // Button: Reset Tracking
  btnReset.addEventListener('click', async () => {
    try {
      btnReset.disabled = true;
      btnReset.textContent = 'Mereset...';
      await fetch(resetUrl, { method: 'POST' });
      setTimeout(() => {
        btnReset.disabled = false;
        btnReset.innerHTML = '🔄 Reset Pelacakan';
      }, 500);
    } catch (e) {
      console.error('Failed to reset:', e);
      btnReset.disabled = false;
      btnReset.innerHTML = '🔄 Reset Pelacakan';
    }
  });

  // Modal Controls
  btnSettings.addEventListener('click', () => {
    modalSettings.classList.add('open');
  });

  btnCloseModal.addEventListener('click', () => {
    modalSettings.classList.remove('open');
  });

  modalSettings.addEventListener('click', (e) => {
    if (e.target === modalSettings) {
      modalSettings.classList.remove('open');
    }
  });

  // Save Gemini Key to Server-side
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
        alert('API Key berhasil disimpan di server-side! Model Gemini Live aktif.');
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
});
