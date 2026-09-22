/**
 * SAFEGUARD AI - APD Cards & Industrial Tower Light Component
 */

export class APDVisualizer {
  constructor() {
    // Hero status banner elements
    this.heroCard = document.getElementById('hero-status-card');
    this.heroTitle = document.getElementById('hero-title');
    this.heroDesc = document.getElementById('hero-desc');
    this.heroLabel = document.getElementById('hero-label');

    // Tower light bulbs
    this.bulbRed = document.getElementById('tower-red');
    this.bulbYellow = document.getElementById('tower-yellow');
    this.bulbGreen = document.getElementById('tower-green');

    // APD Cards
    this.helmBadge = document.getElementById('badge-helm');
    this.helmDetail = document.getElementById('detail-helm');

    this.rompiBadge = document.getElementById('badge-rompi');
    this.rompiDetail = document.getElementById('detail-rompi');

    this.celanaBadge = document.getElementById('badge-celana');
    this.celanaDetail = document.getElementById('detail-celana');

    this.sepatuBadge = document.getElementById('badge-sepatu');
    this.sepatuDetail = document.getElementById('detail-sepatu');

    // Audit Log List
    this.logList = document.getElementById('audit-log-list');

    // Tracking progress elements
    this.trackIdBadge = document.getElementById('track-id-badge');
    this.trackStatusText = document.getElementById('track-status-text');
    this.stableProgressFill = document.getElementById('stable-progress-fill');
  }

  update(telemetry) {
    const active = telemetry.active_track;
    const light = telemetry.light || { light_state: 'OFF', message: 'Standby' };

    // 1. Update Tower Light
    this.setTowerLight(light.light_state);

    // 2. Update Active Track Meta & Progress
    if (active && telemetry.has_person) {
      this.trackIdBadge.textContent = `ID #${active.track_id}`;
      this.trackStatusText.textContent = active.reason || active.state;
      
      const pct = Math.min((active.stable_frames / 4) * 100, 100);
      this.stableProgressFill.style.width = `${pct}%`;
      this.stableProgressFill.style.background = active.is_full_body ? 'var(--color-green)' : 'var(--color-amber)';
    } else {
      this.trackIdBadge.textContent = 'ID: -';
      this.trackStatusText.textContent = 'Menunggu subjek di zona inspeksi';
      this.stableProgressFill.style.width = '0%';
    }

    // 3. Update Hero Status Card
    this.updateHeroStatus(active, light);

    // 4. Update APD 4-Item Cards
    if (active && active.vlm_result) {
      this.renderVLMResult(active.vlm_result);
    } else if (active && !active.is_full_body) {
      this.setCardsWarning();
    } else {
      this.resetCards();
    }

    // 5. Update Audit Log
    if (telemetry.history) {
      this.renderAuditLog(telemetry.history);
    }
  }

  setTowerLight(state) {
    this.bulbRed.classList.remove('active');
    this.bulbYellow.classList.remove('active');
    this.bulbGreen.classList.remove('active');

    if (state === 'GREEN') {
      this.bulbGreen.classList.add('active');
    } else if (state === 'RED') {
      this.bulbRed.classList.add('active');
    } else if (state === 'YELLOW' || state === 'STEP_BACK') {
      this.bulbYellow.classList.add('active');
    }
  }

  updateHeroStatus(active, light) {
    this.heroCard.className = 'hero-status-card';

    if (!active || !active.track_id) {
      this.heroCard.classList.add('state-idle');
      this.heroLabel.textContent = 'STATUS SISTEM';
      this.heroTitle.textContent = 'STANDBY';
      this.heroDesc.textContent = 'Silakan berdiri di depan kamera hingga seluruh tubuh terlihat.';
      return;
    }

    if (!active.is_full_body) {
      this.heroCard.classList.add('state-amber');
      this.heroLabel.textContent = 'PERINGATAN POSISI';
      this.heroTitle.textContent = 'SILAKAN MUNDUR';
      this.heroDesc.textContent = active.reason || 'Tubuh belum terlihat utuh dari kepala hingga sepatu.';
      this.setTowerLight('YELLOW');
      return;
    }

    if (active.state === 'ANALYZING') {
      this.heroCard.classList.add('state-amber');
      this.heroLabel.textContent = 'MEMPROSES VLM';
      this.heroTitle.textContent = 'MENGANALISA APD...';
      this.heroDesc.textContent = 'AI sedang memverifikasi helm, rompi, celana, dan sepatu.';
      return;
    }

    if (active.vlm_result) {
      const res = active.vlm_result;
      if (res.is_complete) {
        this.heroCard.classList.add('state-green');
        this.heroLabel.textContent = 'HASIL VERIFIKASI';
        this.heroTitle.textContent = 'AKSES DIIZINKAN';
        this.heroDesc.textContent = 'Semua APD lengkap sesuai standar K3. Silakan masuk.';
      } else {
        this.heroCard.classList.add('state-red');
        this.heroLabel.textContent = 'HASIL VERIFIKASI';
        this.heroTitle.textContent = 'AKSES DITOLAK';
        const missing = res.missing_items.length > 0 ? res.missing_items.join(', ') : 'Kelengkapan APD belum sesuai';
        this.heroDesc.textContent = `Belum memenuhi syarat: ${missing}.`;
      }
    }
  }

  renderVLMResult(res) {
    // 1. Helm (Warna bebas, asalkan safety helmet)
    if (res.helm.detected) {
      this.helmBadge.className = 'apd-status-badge badge-green';
      this.helmBadge.textContent = 'TERDETEKSI';
      this.helmDetail.textContent = res.helm.description || 'Helm keselamatan terpasang';
    } else {
      this.helmBadge.className = 'apd-status-badge badge-red';
      this.helmBadge.textContent = 'TIDAK ADA';
      this.helmDetail.textContent = 'Wajib memakai helm keselamatan';
    }

    // 2. Rompi (Wajib Orange / Kuning)
    if (res.rompi.detected && res.rompi.is_valid_color) {
      this.rompiBadge.className = 'apd-status-badge badge-green';
      this.rompiBadge.textContent = 'VALID';
      this.rompiDetail.textContent = `Rompi warna ${res.rompi.color} reflektif`;
    } else if (res.rompi.detected && !res.rompi.is_valid_color) {
      this.rompiBadge.className = 'apd-status-badge badge-red';
      this.rompiBadge.textContent = 'WARNA TIDAK SAH';
      this.rompiDetail.textContent = `Warna ${res.rompi.color} ditolak. Wajib orange atau kuning.`;
    } else {
      this.rompiBadge.className = 'apd-status-badge badge-red';
      this.rompiBadge.textContent = 'TIDAK ADA';
      this.rompiDetail.textContent = 'Wajib memakai rompi orange atau kuning';
    }

    // 3. Celana Panjang
    if (res.celana_panjang.detected) {
      this.celanaBadge.className = 'apd-status-badge badge-green';
      this.celanaBadge.textContent = 'MEMENUHI';
      this.celanaDetail.textContent = res.celana_panjang.description || 'Celana panjang terpasang';
    } else {
      this.celanaBadge.className = 'apd-status-badge badge-red';
      this.celanaBadge.textContent = 'DITOLAK';
      this.celanaDetail.textContent = 'Celana pendek tidak diizinkan';
    }

    // 4. Sepatu Tertutup
    if (res.sepatu_tertutup.detected && res.sepatu_tertutup.is_closed_shoes) {
      this.sepatuBadge.className = 'apd-status-badge badge-green';
      this.sepatuBadge.textContent = 'TERTUTUP';
      this.sepatuDetail.textContent = res.sepatu_tertutup.description || 'Sepatu tertutup terpasang';
    } else {
      this.sepatuBadge.className = 'apd-status-badge badge-red';
      this.sepatuBadge.textContent = 'TIDAK SAH';
      this.sepatuDetail.textContent = 'Sandal atau telanjang kaki dilarang';
    }
  }

  setCardsWarning() {
    this.helmBadge.className = 'apd-status-badge badge-neutral';
    this.helmBadge.textContent = 'MENUNGGU';
    this.helmDetail.textContent = 'Mundur agar seluruh tubuh terlihat';

    this.rompiBadge.className = 'apd-status-badge badge-neutral';
    this.rompiBadge.textContent = 'MENUNGGU';
    this.rompiDetail.textContent = 'Mundur agar seluruh tubuh terlihat';

    this.celanaBadge.className = 'apd-status-badge badge-neutral';
    this.celanaBadge.textContent = 'MENUNGGU';
    this.celanaDetail.textContent = 'Mundur agar seluruh tubuh terlihat';

    this.sepatuBadge.className = 'apd-status-badge badge-neutral';
    this.sepatuBadge.textContent = 'MENUNGGU';
    this.sepatuDetail.textContent = 'Mundur agar seluruh tubuh terlihat';
  }

  resetCards() {
    const reset = (badge, detail) => {
      badge.className = 'apd-status-badge badge-neutral';
      badge.textContent = 'STANDBY';
      detail.textContent = 'Menunggu deteksi pekerja';
    };
    reset(this.helmBadge, this.helmDetail);
    reset(this.rompiBadge, this.rompiDetail);
    reset(this.celanaBadge, this.celanaDetail);
    reset(this.sepatuBadge, this.sepatuDetail);
  }

  renderAuditLog(history) {
    if (!history || history.length === 0) {
      this.logList.innerHTML = '<div style="color:var(--text-muted); font-size:0.8rem; padding:0.5rem;">Belum ada riwayat inspeksi</div>';
      return;
    }

    this.logList.innerHTML = history.map(item => {
      const badgeClass = item.is_complete ? 'badge-green' : 'badge-red';
      const statusText = item.is_complete ? 'LENGKAP' : 'TIDAK LENGKAP';
      const sourceIcon = item.inference_source === 'GEMINI_LIVE' ? '🌐' : '⚡';
      const timeMs = item.inference_time_ms ? `${item.inference_time_ms}ms` : '';
      return `
        <div class="log-item">
          <div style="display:flex; align-items:center; gap:0.6rem;">
            <span class="log-time">${item.timestamp}</span>
            <span style="font-weight:600;">Pekerja #${item.track_id}</span>
            <span style="font-size:0.72rem; color:var(--text-muted); font-family:var(--font-mono);">${sourceIcon} ${timeMs}</span>
          </div>
          <span class="apd-status-badge ${badgeClass}">${statusText}</span>
        </div>
      `;
    }).join('');

  }
}
