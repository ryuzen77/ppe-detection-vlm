/**
 * DEPRO - HUD Overlay Canvas Renderer (60 FPS)
 */

export class HUDOverlay {
  constructor(canvasElement) {
    this.canvas = canvasElement;
    this.ctx = this.canvas.getContext('2d');
    this.latestDetections = [];
    this.corridor = { enabled: true, left_ratio: 0.28, right_ratio: 0.72 };
    this.guidesVisible = true;
    this.frameWidth = 1280;
    this.frameHeight = 720;
    this.resizeCanvas();
    window.addEventListener('resize', () => this.resizeCanvas());
  }

  setGuidesVisible(visible) {
    this.guidesVisible = !!visible;
    this.render();
  }

  resizeCanvas() {
    this.canvas.width = this.canvas.parentElement.clientWidth;
    this.canvas.height = this.canvas.parentElement.clientHeight;
  }

  setFrameDimensions(width, height) {
    if (width > 0 && height > 0) {
      this.frameWidth = width;
      this.frameHeight = height;
    }
  }

  setCorridor(corridor) {
    if (corridor) {
      this.corridor = corridor;
    }
  }

  setDetections(detections) {
    this.latestDetections = detections || [];
    this.render();
  }

  /**
   * Video ditampilkan dengan `object-fit: contain`, jadi kalau rasio kamera tidak
   * sama dengan rasio viewport akan muncul bilah hitam. Overlay harus memakai
   * kotak video yang sebenarnya, bukan seluruh kanvas, agar tidak bergeser.
   */
  computeFit() {
    const { width, height } = this.canvas;
    const frameW = this.frameWidth || 1280;
    const frameH = this.frameHeight || 720;
    const scale = Math.min(width / frameW, height / frameH);
    const drawW = frameW * scale;
    const drawH = frameH * scale;
    return {
      scale,
      drawW,
      drawH,
      offsetX: (width - drawW) / 2,
      offsetY: (height - drawH) / 2
    };
  }

  render() {
    const { width, height } = this.canvas;
    this.ctx.clearRect(0, 0, width, height);

    const fit = this.computeFit();
    const { scale, drawW, drawH, offsetX, offsetY } = fit;

    // 1. Draw Virtual Corridor guides if enabled & visible
    if (this.guidesVisible && this.corridor && this.corridor.enabled) {
      const cx1 = offsetX + drawW * this.corridor.left_ratio;
      const cx2 = offsetX + drawW * this.corridor.right_ratio;

      // Darken outside regions slightly
      this.ctx.fillStyle = 'rgba(10, 13, 20, 0.45)';
      this.ctx.fillRect(offsetX, offsetY, cx1 - offsetX, drawH);
      this.ctx.fillRect(cx2, offsetY, offsetX + drawW - cx2, drawH);

      // Vertical neon dashed lines
      this.ctx.strokeStyle = 'rgba(255, 200, 0, 0.7)';
      this.ctx.lineWidth = 2;
      this.ctx.setLineDash([8, 6]);

      this.ctx.beginPath();
      this.ctx.moveTo(cx1, offsetY);
      this.ctx.lineTo(cx1, offsetY + drawH);
      this.ctx.stroke();

      this.ctx.beginPath();
      this.ctx.moveTo(cx2, offsetY);
      this.ctx.lineTo(cx2, offsetY + drawH);
      this.ctx.stroke();

      this.ctx.setLineDash([]); // Reset dash

      // Draw Industrial Footprint Standoff Guide Zone at corridor bottom
      this.drawFootprintZone(offsetY + drawH, drawH, cx1, cx2);
    }

    if (!this.latestDetections || this.latestDetections.length === 0) {
      return;
    }

    for (const det of this.latestDetections) {
      const [x1, y1, x2, y2] = det.bbox;
      const bx = offsetX + x1 * scale;
      const by = offsetY + y1 * scale;
      const bw = (x2 - x1) * scale;
      const bh = (y2 - y1) * scale;

      const isInside = det.is_inside_corridor !== undefined ? det.is_inside_corridor : true;
      let color = '#888888';
      let statusLabel = 'DI LUAR JALUR';

      if (isInside) {
        if (det.is_full_body) {
          color = '#00e699';
          statusLabel = 'POSISI PAS (FULL BODY)';
        } else {
          color = '#ff3366';
          if (det.clip_type === 'HEAD_CLIPPED') {
            statusLabel = 'MUNDUR SEDIKIT (KEPALA)';
          } else if (det.clip_type === 'FEET_CLIPPED') {
            statusLabel = 'MUNDUR 1 LANGKAH (KAKI)';
          } else if (det.clip_type === 'TOO_FAR') {
            statusLabel = 'SILAKAN MENDEKAT';
          } else {
            statusLabel = 'MUNDUR (TERPOTONG)';
          }
        }
      }

      // 1. Draw corner brackets
      this.drawCornerBrackets(bx, by, bw, bh, color);

      // 2. Draw Keypoints if inside corridor
      if (isInside && det.keypoints && Array.isArray(det.keypoints)) {
        this.drawPoseSkeleton(det.keypoints, fit, color);
      }

      // 3. Draw Track Badge
      this.drawTrackBadge(bx, by, det.track_id, statusLabel, color);
    }
  }

  drawFootprintZone(videoBottom, drawH, cx1, cx2) {
    const zoneW = (cx2 - cx1) * 0.65;
    const zoneH = Math.min(drawH * 0.16, 110);
    const zoneX = cx1 + ((cx2 - cx1) - zoneW) / 2;
    const zoneY = videoBottom - zoneH - 22;

    this.ctx.save();
    this.ctx.strokeStyle = 'rgba(0, 230, 153, 0.45)';
    this.ctx.fillStyle = 'rgba(0, 230, 153, 0.05)';
    this.ctx.lineWidth = 1.5;
    this.ctx.setLineDash([6, 5]);

    this.ctx.strokeRect(zoneX, zoneY, zoneW, zoneH);
    this.ctx.fillRect(zoneX, zoneY, zoneW, zoneH);

    this.ctx.setLineDash([]);
    this.ctx.font = '600 11px "Outfit", sans-serif';
    this.ctx.fillStyle = 'rgba(0, 230, 153, 0.9)';
    this.ctx.textAlign = 'center';
    this.ctx.fillText('👣 AREA JEJAK KAKI (BERDIRI DI SINI)', zoneX + zoneW / 2, zoneY + zoneH / 2 + 4);
    this.ctx.restore();
  }

  drawCornerBrackets(x, y, w, h, color) {
    const len = Math.min(w, h) * 0.15;
    this.ctx.strokeStyle = color;
    this.ctx.lineWidth = 3;
    this.ctx.shadowColor = color;
    this.ctx.shadowBlur = 8;

    // Top-Left
    this.ctx.beginPath();
    this.ctx.moveTo(x, y + len);
    this.ctx.lineTo(x, y);
    this.ctx.lineTo(x + len, y);
    this.ctx.stroke();

    // Top-Right
    this.ctx.beginPath();
    this.ctx.moveTo(x + w - len, y);
    this.ctx.lineTo(x + w, y);
    this.ctx.lineTo(x + w, y + len);
    this.ctx.stroke();

    // Bottom-Left
    this.ctx.beginPath();
    this.ctx.moveTo(x, y + h - len);
    this.ctx.lineTo(x, y + h);
    this.ctx.lineTo(x + len, y + h);
    this.ctx.stroke();

    // Bottom-Right
    this.ctx.beginPath();
    this.ctx.moveTo(x + w - len, y + h);
    this.ctx.lineTo(x + w, y + h);
    this.ctx.lineTo(x + w, y + h - len);
    this.ctx.stroke();

    this.ctx.shadowBlur = 0;
  }

  drawPoseSkeleton(kpts, fit, color) {
    this.ctx.fillStyle = color;
    for (let i = 0; i < kpts.length; i++) {
      const [kx, ky, conf] = kpts[i];
      if (conf > 0.4) {
        this.ctx.beginPath();
        this.ctx.arc(fit.offsetX + kx * fit.scale, fit.offsetY + ky * fit.scale, 3, 0, 2 * Math.PI);
        this.ctx.fill();
      }
    }
  }

  drawTrackBadge(x, y, trackId, label, color) {
    const text = `#${trackId} ${label}`;
    this.ctx.font = '600 12px "Outfit", sans-serif';
    const textWidth = this.ctx.measureText(text).width;

    this.ctx.fillStyle = 'rgba(10, 13, 20, 0.85)';
    this.ctx.fillRect(x, Math.max(10, y - 24), textWidth + 14, 20);

    this.ctx.strokeStyle = color;
    this.ctx.lineWidth = 1;
    this.ctx.strokeRect(x, Math.max(10, y - 24), textWidth + 14, 20);

    this.ctx.fillStyle = color;
    this.ctx.fillText(text, x + 7, Math.max(10, y - 24) + 14);
  }
}
