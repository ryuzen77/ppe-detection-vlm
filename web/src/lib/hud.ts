/**
 * Overlay di atas video: jalur inspeksi, area pijakan, dan kotak tiap orang.
 *
 * Video ditampilkan dengan object-fit: contain, jadi koordinat frame kamera
 * dipetakan ke kotak video sebenarnya (bukan seluruh kanvas) agar tidak bergeser.
 * Warna mengikuti aturan status: hijau = posisi pas, kuning = perlu arahan
 * (merah khusus APD kurang), abu = di luar jalur.
 */
import type { Detection, Telemetry } from './api/types'

export interface Fit {
  scale: number
  drawW: number
  drawH: number
  offsetX: number
  offsetY: number
}

export function computeFit(canvasW: number, canvasH: number, frameW: number, frameH: number): Fit {
  const fw = frameW > 0 ? frameW : 1280
  const fh = frameH > 0 ? frameH : 720
  const scale = Math.min(canvasW / fw, canvasH / fh)
  const drawW = fw * scale
  const drawH = fh * scale
  return { scale, drawW, drawH, offsetX: (canvasW - drawW) / 2, offsetY: (canvasH - drawH) / 2 }
}

const COLORS = { ok: '#22c55e', warn: '#f5a524', out: '#8b939c' }

export function detectionStyle(d: Detection): { color: string; label: string } {
  if (!d.is_inside_corridor) return { color: COLORS.out, label: 'di luar jalur' }
  if (d.is_full_body) return { color: COLORS.ok, label: 'posisi pas' }
  const label = d.clip_type === 'HEAD_CLIPPED' ? 'mundur sedikit'
    : d.clip_type === 'FEET_CLIPPED' ? 'mundur 1 langkah'
    : d.clip_type === 'TOO_FAR' ? 'mendekat'
    : 'mundur'
  return { color: COLORS.warn, label }
}

export function drawHud(ctx: CanvasRenderingContext2D, w: number, h: number, t: Telemetry | null, guides: boolean): void {
  ctx.clearRect(0, 0, w, h)
  if (!t) return
  const fit = computeFit(w, h, t.frame_width, t.frame_height)
  const { offsetX, offsetY, drawW, drawH, scale } = fit

  if (guides && t.corridor?.enabled) {
    const x1 = offsetX + drawW * t.corridor.left_ratio
    const x2 = offsetX + drawW * t.corridor.right_ratio
    ctx.fillStyle = 'rgba(8, 10, 12, 0.45)'
    ctx.fillRect(offsetX, offsetY, x1 - offsetX, drawH)
    ctx.fillRect(x2, offsetY, offsetX + drawW - x2, drawH)
    ctx.strokeStyle = 'rgba(230, 232, 235, 0.55)'
    ctx.lineWidth = 1.5
    ctx.setLineDash([6, 6])
    for (const x of [x1, x2]) {
      ctx.beginPath()
      ctx.moveTo(x, offsetY)
      ctx.lineTo(x, offsetY + drawH)
      ctx.stroke()
    }
    // Area pijakan di dasar jalur
    const zoneW = (x2 - x1) * 0.65
    const zoneH = Math.min(drawH * 0.14, 90)
    const zx = x1 + (x2 - x1 - zoneW) / 2
    const zy = offsetY + drawH - zoneH - 16
    ctx.strokeStyle = 'rgba(34, 197, 94, 0.5)'
    ctx.strokeRect(zx, zy, zoneW, zoneH)
    ctx.setLineDash([])
    ctx.fillStyle = 'rgba(34, 197, 94, 0.85)'
    ctx.font = '600 11px "Inter Variable", system-ui, sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText('BERDIRI DI SINI', zx + zoneW / 2, zy + zoneH / 2 + 4)
    ctx.textAlign = 'left'
  }

  for (const d of t.detections ?? []) {
    const [bx1, by1, bx2, by2] = d.bbox
    const x = offsetX + bx1 * scale
    const y = offsetY + by1 * scale
    const bw = (bx2 - bx1) * scale
    const bh = (by2 - by1) * scale
    const { color, label } = detectionStyle(d)
    drawBrackets(ctx, x, y, bw, bh, color)
    if (d.is_inside_corridor && d.keypoints) {
      ctx.fillStyle = color
      for (const [kx, ky, conf] of d.keypoints) {
        if (conf > 0.4) {
          ctx.beginPath()
          ctx.arc(offsetX + kx * scale, offsetY + ky * scale, 2.5, 0, Math.PI * 2)
          ctx.fill()
        }
      }
    }
    drawBadge(ctx, x, y, `#${d.track_id} · ${label}`, color)
  }
}

function drawBrackets(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, color: string): void {
  const len = Math.min(w, h) * 0.14
  ctx.strokeStyle = color
  ctx.lineWidth = 2.5
  const corners: [number, number, number, number][] = [
    [x, y, 1, 1], [x + w, y, -1, 1], [x, y + h, 1, -1], [x + w, y + h, -1, -1],
  ]
  for (const [cx, cy, dx, dy] of corners) {
    ctx.beginPath()
    ctx.moveTo(cx, cy + dy * len)
    ctx.lineTo(cx, cy)
    ctx.lineTo(cx + dx * len, cy)
    ctx.stroke()
  }
}

function drawBadge(ctx: CanvasRenderingContext2D, x: number, y: number, text: string, color: string): void {
  ctx.font = '600 12px "Inter Variable", system-ui, sans-serif'
  const tw = ctx.measureText(text).width
  const by = Math.max(6, y - 24)
  ctx.fillStyle = 'rgba(14, 16, 18, 0.85)'
  ctx.fillRect(x, by, tw + 14, 20)
  ctx.fillStyle = color
  ctx.fillRect(x, by, 3, 20)
  ctx.fillStyle = '#e6e8eb'
  ctx.fillText(text, x + 9, by + 14)
}
