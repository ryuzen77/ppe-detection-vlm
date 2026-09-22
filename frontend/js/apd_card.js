/**
 * ===================================================================
 * SAFEGUARD AI - APD Cards & Stepper Guidance Visualizer (60 FPS)
 * Sesuai Desain Mockup Enterprise K3
 * ===================================================================
 */

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

    this.badgeHelm = document.getElementById('badge-helm');
    this.textHelm = document.getElementById('text-helm');

    this.badgeRompi = document.getElementById('badge-rompi');
    this.textRompi = document.getElementById('text-rompi');

    this.badgeCelana = document.getElementById('badge-celana');
    this.textCelana = document.getElementById('text-celana');

    this.badgeSepatu = document.getElementById('badge-sepatu');
    this.textSepatu = document.getElementById('text-sepatu');

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
    if (this.techEngineMode) {
      this.techEngineMode.textContent = telemetry.engine_mode || 'HYBRID_AUTO';
    }
    if (this.techActiveTrack) {
      this.techActiveTrack.textContent = active ? `#${active.track_id}` : 'None';
    }
    if (this.techStability && active) {
      this.techStability.textContent = `${active.stable_frames || 0} / 2`;
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
      this.guidancePillText.textContent = 'AI sedang memverifikasi helm, rompi, celana, dan sepatu';

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

  renderChecklistResult(res) {
    // 1. Helm
    if (res.helm.detected) {
      this.badgeHelm.className = 'row-badge status-ok';
      this.badgeHelm.innerHTML = '<span class="badge-icon">✅</span> Terpasang';
    } else {
      this.badgeHelm.className = 'row-badge status-fail';
      this.badgeHelm.innerHTML = '<span class="badge-icon">❌</span> Tidak Ada';
    }

    // 2. Rompi
    if (res.rompi.detected && res.rompi.is_valid_color) {
      this.badgeRompi.className = 'row-badge status-ok';
      this.badgeRompi.innerHTML = `<span class="badge-icon">✅</span> ${res.rompi.color || 'OK'}`;
    } else if (res.rompi.detected && !res.rompi.is_valid_color) {
      this.badgeRompi.className = 'row-badge status-fail';
      this.badgeRompi.innerHTML = `<span class="badge-icon">❌</span> Bukan Hi-Vis`;
    } else {
      this.badgeRompi.className = 'row-badge status-fail';
      this.badgeRompi.innerHTML = '<span class="badge-icon">❌</span> Tidak Ada';
    }

    // 3. Celana Panjang
    if (res.celana_panjang.detected) {
      this.badgeCelana.className = 'row-badge status-ok';
      this.badgeCelana.innerHTML = '<span class="badge-icon">✅</span> Panjang';
    } else {
      this.badgeCelana.className = 'row-badge status-fail';
      this.badgeCelana.innerHTML = '<span class="badge-icon">❌</span> Pendek';
    }

    // 4. Sepatu Tertutup
    if (res.sepatu_tertutup.detected && res.sepatu_tertutup.is_closed_shoes) {
      this.badgeSepatu.className = 'row-badge status-ok';
      this.badgeSepatu.innerHTML = '<span class="badge-icon">✅</span> Tertutup';
    } else {
      this.badgeSepatu.className = 'row-badge status-fail';
      this.badgeSepatu.innerHTML = '<span class="badge-icon">❌</span> Terbuka/Sandal';
    }

    if (res.is_complete) {
      this.checklistFootnoteText.textContent = 'Semua APD lengkap sesuai standar K3.';
    } else {
      const missingStr = res.missing_items.length > 0 ? res.missing_items.join(', ') : 'Belum lengkap';
      this.checklistFootnoteText.textContent = `Belum memenuhi syarat: ${missingStr}`;
    }
  }

  resetChecklist(active) {
    this.badgeHelm.className = 'row-badge status-pending';
    this.badgeHelm.innerHTML = '<span class="badge-icon">🕒</span> Belum dinilai';

    this.badgeRompi.className = 'row-badge status-pending';
    this.badgeRompi.innerHTML = '<span class="badge-icon">🕒</span> Belum dinilai';

    this.badgeCelana.className = 'row-badge status-pending';
    this.badgeCelana.innerHTML = '<span class="badge-icon">🕒</span> Belum dinilai';

    this.badgeSepatu.className = 'row-badge status-pending';
    this.badgeSepatu.innerHTML = '<span class="badge-icon">🕒</span> Belum dinilai';

    if (active && !active.is_full_body) {
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

      const statusBadge = rec.is_complete 
        ? '<span style="color:var(--accent-teal); font-weight:700;">✅ Lengkap</span>'
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
