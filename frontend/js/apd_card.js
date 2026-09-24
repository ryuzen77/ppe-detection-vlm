/**
 * ===================================================================
 * SAFEGUARD AI - APD Cards & Stepper Guidance Visualizer (60 FPS)
 * Sesuai Desain Mockup Enterprise K3
 * ===================================================================
 */

import { assessItem } from './ppe_catalog.js';

export class APDVisualizer {
  constructor() {
    // 1. Guidance Banner & Stepper Elements
    this.guidanceCard = document.getElementById('guidance-card');
    this.guidanceIcon = document.getElementById('guidance-icon-symbol');
    this.guidanceEyebrow = document.getElementById('guidance-eyebrow');
    this.guidanceTitle = document.getElementById('guidance-main-title');
    this.guidanceSubText = document.getElementById('guidance-sub-text');
    this.guidancePillText = document.getElementById('guidance-pill-text');

    this.step1 = document.getElementById('step-1');
    this.step2 = document.getElementById('step-2');
    this.step3 = document.getElementById('step-3');
    this.line12 = document.getElementById('line-1-2');
    this.line23 = document.getElementById('line-2-3');

    // 2. Checklist Elements
    this.checklistSubjectChip = document.getElementById('checklist-subject-chip');
    this.checklistFootnoteText = document.getElementById('checklist-footnote-text');

    // Baris checklist dibangun dari katalog APD lewat setCatalog()
    this.checklistRows = document.getElementById('checklist-rows');
    this.catalog = [];
    this.rowBadges = {};

    // 3. Recent History Elements
    this.recentEmptyState = document.getElementById('recent-empty-state');
    this.recentListGroup = document.getElementById('recent-list-group');

    // 4. Video Viewport Overlays & Tech Details
    this.hudSubjectBadge = document.getElementById('hud-subject-badge');
    this.techEngineMode = document.getElementById('tech-engine-mode');
    this.techLatencyMs = document.getElementById('tech-latency-ms');
    this.techActiveTrack = document.getElementById('tech-active-track');
    this.techStability = document.getElementById('tech-stability');
  }

  /** Membangun satu baris checklist per item katalog. */
  setCatalog(items) {
    this.catalog = items;
    this.rowBadges = {};
    this.checklistRows.innerHTML = '';

    items.forEach((item) => {
      const row = document.createElement('div');
      row.className = 'checklist-row';

      const left = document.createElement('div');
      left.className = 'row-left';
      // Indikator di samping ikon: kuning = belum dinilai, hijau = ada, merah = tidak ada
      const dot = document.createElement('span');
      dot.setAttribute('role', 'img');
      const emoji = document.createElement('span');
      emoji.className = 'item-emoji';
      emoji.textContent = item.icon;
      const name = document.createElement('span');
      name.className = 'item-name';
      name.textContent = item.label;
      left.append(dot, emoji, name);

      const badge = document.createElement('div');
      badge._dot = dot;
      row.append(left, badge);
      this.checklistRows.appendChild(row);
      this.rowBadges[item.key] = badge;
      this._setBadge(badge, 'status-pending', '🕒', 'Belum dinilai');
    });
  }

  /** Teks proses analisa, mis. "helm, rompi, celana, dan sepatu". */
  _itemSummary() {
    const names = this.catalog.map((item) => item.short_label.toLowerCase());
    if (names.length <= 1) return names.join('');
    return `${names.slice(0, -1).join(', ')}, dan ${names[names.length - 1]}`;
  }

  _setBadge(badge, statusClass, icon, text) {
    if (badge._dot) {
      const tone = statusClass === 'status-ok' ? 'ok' : statusClass === 'status-fail' ? 'fail' : 'pending';
      badge._dot.className = `apd-dot apd-dot-${tone}`;
      badge._dot.setAttribute('aria-label', { ok: 'Ada', fail: 'Tidak ada', pending: 'Belum dinilai' }[tone]);
    }
    badge.className = `row-badge ${statusClass}`;
    badge.innerHTML = '';
    const iconEl = document.createElement('span');
    iconEl.className = 'badge-icon';
    iconEl.textContent = icon;
    const textEl = document.createElement('span');
    textEl.className = 'badge-text';
    textEl.textContent = text;
    badge.append(iconEl, textEl);
  }

  update(telemetry) {
    const active = telemetry.active_track;
    const light = telemetry.light || { light_state: 'OFF', message: 'Standby' };

    // Update Video Subject Badge
    if (active && active.track_id) {
      this.hudSubjectBadge.textContent = `Subjek #${active.track_id}`;
      this.checklistSubjectChip.textContent = `Subjek #${active.track_id}`;
    } else {
      this.hudSubjectBadge.textContent = 'Subjek: -';
      this.checklistSubjectChip.textContent = 'Subjek: -';
    }

    // Update Technical Details Drawer
    if (this.techEngineMode && telemetry.api_monitor) {
      this.techEngineMode.textContent = telemetry.api_monitor.mode || '-';
    }
    if (this.techActiveTrack) {
      this.techActiveTrack.textContent = active ? `#${active.track_id}` : 'None';
    }
    if (this.techStability) {
      // Target diambil dari server (STABLE_FRAMES_REQUIRED), bukan ditulis tetap
      const required = telemetry.stable_frames_required ?? '?';
      this.techStability.textContent = `${active ? (active.stable_frames || 0) : 0} / ${required}`;
    }

    // Update Guidance Card & Stepper
    this.updateGuidance(active, light);

    // Update APD 4-Item Checklist
    if (active && active.vlm_result) {
      this.renderChecklistResult(active.vlm_result);
      if (this.techLatencyMs) {
        this.techLatencyMs.textContent = `${active.vlm_result.inference_time_ms || 0} ms`;
      }
    } else {
      this.resetChecklist(active);
      if (this.techLatencyMs) {
        this.techLatencyMs.textContent = '—';
      }
    }

    // Update Recent History Log
    if (telemetry.history) {
      this.renderRecentHistory(telemetry.history);
    }
  }

  updateGuidance(active, light) {
    // Reset stepper classes
    this.step1.className = 'step-node';
    this.step2.className = 'step-node';
    this.step3.className = 'step-node';
    this.line12.className = 'step-connector';
    this.line23.className = 'step-connector';

    this.guidanceCard.className = 'card-guidance';

    // State A: Standby (Tidak ada orang di lorong)
    if (!active || !active.track_id) {
      this.guidanceCard.classList.add('state-adjust');
      this.guidanceIcon.textContent = '👤';
      this.guidanceEyebrow.textContent = 'PANDUAN OPERATOR';
      this.guidanceTitle.textContent = 'Menunggu Pekerja';
      this.guidanceSubText.textContent = 'Pekerja silakan berdiri di dalam lorong inspeksi.';
      this.guidancePillText.textContent = 'Pemeriksaan belum dimulai';

      this.step1.classList.add('active');
      return;
    }

    // State A2: Sistem gangguan — utama & cadangan VLM tidak menjawab. Belum ada
    // keputusan: pekerja diminta menunggu, pemeriksaan diulang otomatis (T27).
    if (active.state === 'WAITING_SYSTEM') {
      this.guidanceCard.classList.add('state-adjust');
      this.guidanceIcon.textContent = '⏳';
      this.guidanceEyebrow.textContent = 'SISTEM GANGGUAN';
      this.guidanceTitle.textContent = 'Mohon Tunggu';
      this.guidanceSubText.textContent = 'Sistem pemeriksaan sedang gangguan. Bila sudah aktif, silakan berdiri di batas pemeriksaan.';
      this.guidancePillText.textContent = active.retry_in_s != null
        ? `Pemeriksaan diulang otomatis dalam ${Math.ceil(active.retry_in_s)} dtk`
        : 'Pemeriksaan diulang otomatis';
      this.step1.classList.add('complete');
      this.line12.classList.add('active');
      this.step2.classList.add('active');
      return;
    }

    // State B: Peringatan Posisi (Terpotong / Kaki belum terlihat)
    if (!active.is_full_body) {
      this.guidanceCard.classList.add('state-adjust');
      this.guidanceEyebrow.textContent = 'SESUAIKAN POSISI';
      
      if (active.clip_type === 'HEAD_CLIPPED') {
        this.guidanceIcon.textContent = '👤↓';
        this.guidanceTitle.textContent = 'Mundur sedikit';
        this.guidanceSubText.textContent = 'Kepala terlalu dekat dengan kamera.';
      } else if (active.clip_type === 'FEET_CLIPPED') {
        this.guidanceIcon.textContent = '👤←';
        this.guidanceTitle.textContent = 'Mundur satu langkah';
        this.guidanceSubText.textContent = 'Kepala hingga kaki harus terlihat di kamera.';
      } else if (active.clip_type === 'TOO_FAR') {
        this.guidanceIcon.textContent = '👤→';
        this.guidanceTitle.textContent = 'Silakan mendekat';
        this.guidanceSubText.textContent = 'Posisi Anda terlalu jauh dari kamera.';
      } else {
        this.guidanceIcon.textContent = '👤←';
        this.guidanceTitle.textContent = 'Silakan mundur';
        this.guidanceSubText.textContent = active.reason || 'Posisikan seluruh tubuh di dalam kamera.';
      }

      this.guidancePillText.textContent = 'Pemeriksaan belum dimulai (menunggu posisi pas)';
      this.step1.classList.add('active');
      return;
    }

    // State C: Stabilizing / Sedang Menganalisis VLM (Step 2 Active)
    if (active.state === 'ANALYZING' || active.state === 'STABILIZING') {
      this.guidanceCard.classList.add('state-adjust');
      this.guidanceIcon.textContent = '⚡';
      this.guidanceEyebrow.textContent = 'PROSES PEMERIKSAAN';
      this.guidanceTitle.textContent = 'Menganalisis APD...';
      this.guidanceSubText.textContent = 'Posisi tubuh sudah pas. Mohon tetap tenang sejenak.';
      this.guidancePillText.textContent = this.catalog.length > 0
        ? `AI sedang memverifikasi ${this._itemSummary()}`
        : 'AI sedang memverifikasi kelengkapan APD';

      this.step1.classList.add('complete');
      this.line12.classList.add('active');
      this.step2.classList.add('active');
      return;
    }

    // State D: Hasil Analisis Selesai (Step 3 Active)
    if (active.vlm_result) {
      const res = active.vlm_result;
      this.step1.classList.add('complete');
      this.line12.classList.add('active');
      this.step2.classList.add('complete');
      this.line23.classList.add('active');
      this.step3.classList.add('complete');

      if (res.is_complete) {
        this.guidanceCard.classList.add('state-success');
        this.guidanceIcon.textContent = '✓';
        this.guidanceEyebrow.textContent = 'HASIL PEMERIKSAAN';
        this.guidanceTitle.textContent = 'Akses Diizinkan';
        this.guidanceSubText.textContent = 'Seluruh APD wajib telah lengkap sesuai standar K3.';
        this.guidancePillText.textContent = 'APD Lengkap - Gerbang dibuka';
      } else {
        this.guidanceCard.classList.add('state-danger');
        this.guidanceIcon.textContent = '✕';
        this.guidanceEyebrow.textContent = 'HASIL PEMERIKSAAN';
        this.guidanceTitle.textContent = 'Akses Ditolak';
        const missing = res.missing_items.length > 0 ? res.missing_items.join(', ') : 'Kelengkapan APD belum sesuai';
        this.guidanceSubText.textContent = `Belum memakai: ${missing}.`;
        this.guidancePillText.textContent = 'Akses Ditolak - Lengkapi APD Anda';
      }
    }
  }

  _escape(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  renderChecklistResult(res) {
    const results = res.items || {};
    this.catalog.forEach((item) => {
      const { ok, text } = assessItem(item, results[item.key]);
      const badge = this.rowBadges[item.key];
      if (ok === null) {
        this._setBadge(badge, 'status-pending', '❔', text);
      } else {
        this._setBadge(badge, ok ? 'status-ok' : 'status-fail', ok ? '✅' : '❌', text);
      }
    });

    const summary = res.is_complete
      ? 'Semua APD lengkap sesuai standar K3.'
      : `Belum memenuhi syarat: ${res.missing_items.length > 0 ? res.missing_items.join(', ') : 'Belum lengkap'}`;

    // Operator perlu tahu bila keputusan diambil VLM cadangan (utama gagal/terputus)
    if (res.decided_by === 'cadangan') {
      this.checklistFootnoteText.innerHTML =
        `${this._escape(summary)} <span class="backup-chip">🛟 Diputuskan VLM cadangan</span>`;
    } else {
      this.checklistFootnoteText.textContent = summary;
    }
  }

  resetChecklist(active) {
    Object.values(this.rowBadges).forEach((badge) => {
      this._setBadge(badge, 'status-pending', '🕒', 'Belum dinilai');
    });

    if (active && active.state === 'WAITING_SYSTEM') {
      this.checklistFootnoteText.textContent = 'Belum dinilai: sistem gangguan, pemeriksaan diulang otomatis.';
    } else if (active && !active.is_full_body) {
      this.checklistFootnoteText.textContent = 'Menunggu posisi tubuh sesuai.';
    } else if (active && active.state === 'ANALYZING') {
      this.checklistFootnoteText.textContent = 'Sedang memindai kelengkapan APD...';
    } else {
      this.checklistFootnoteText.textContent = 'Menunggu subjek di area inspeksi.';
    }
  }

  renderRecentHistory(history) {
    if (!history || history.length === 0) {
      this.recentEmptyState.style.display = 'block';
      this.recentListGroup.style.display = 'none';
      return;
    }

    this.recentEmptyState.style.display = 'none';
    this.recentListGroup.style.display = 'flex';
    this.recentListGroup.innerHTML = '';

    // Ambil maksimal 4 data terbaru
    const recentSlice = history.slice(0, 4);
    recentSlice.forEach(rec => {
      const itemEl = document.createElement('div');
      itemEl.className = 'recent-item-card';

      const unverified = (rec.inference_source || '').startsWith('VLM_GAGAL');
      const statusBadge = rec.is_complete 
        ? '<span style="color:var(--accent-teal); font-weight:700;">✅ Lengkap</span>'
        : unverified
          ? '<span style="color:var(--accent-red); font-weight:700;">⚠️ Tidak terverifikasi</span>'
          : '<span style="color:var(--accent-red); font-weight:700;">❌ Pelanggaran</span>';

      const missingText = rec.missing_items && rec.missing_items.length > 0 
        ? rec.missing_items.join(', ')
        : 'Lolos';

      itemEl.innerHTML = `
        <div style="display:flex; align-items:center; gap:10px;">
          <span style="font-family:var(--font-mono); font-weight:700; color:var(--text-primary);">#${rec.track_id}</span>
          <span style="color:var(--text-muted); font-size:0.75rem;">${rec.timestamp}</span>
        </div>
        <div>${statusBadge}</div>
      `;
      this.recentListGroup.appendChild(itemEl);
    });
  }
}
