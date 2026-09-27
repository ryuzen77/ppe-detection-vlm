/**
 * Overlay di atas video: jalur inspeksi, area pijakan, dan kotak tiap orang.
 *
 * Video ditampilkan dengan object-fit: contain, jadi koordinat frame kamera
 * dipetakan ke kotak video sebenarnya (bukan seluruh kanvas) agar tidak bergeser.
 * Warna diambil dari token CSS (bukan ditulis ulang di sini): hijau = posisi pas,
 * kuning = perlu arahan (merah khusus APD kurang), abu = di luar jalur.
 * Geometri dari settings.ts, teks dari messages.ts, ambang keypoint dari backend.
 */
import type { Detection, Telemetry } from './api/types'
import { HUD as TEXT } from './messages'
import { HUD } from './settings'

export interface Fit {
  scale: number
  drawW: number
  drawH: number
  offsetX: number
  offsetY: number
}

/** Warna overlay, dibaca dari token CSS saat dipakai */
export interface HudPalette {
  ok: string
  warn: string
  outside: string
  text: string
  background: string
  /** Keluarga font UI (token --font-sans) */
  font: string
}

/** Nama token CSS untuk tiap warna overlay (lihat styles/tokens.css) */
const PALETTE_TOKENS: Record<keyof HudPalette, string> = {
  ok: '--ok',
  warn: '--warn',
  outside: '--text-faint',
  text: '--text',
  background: '--bg',
  font: '--font-sans',
}

export function readHudPalette(el: Element = document.documentElement): HudPalette {
  const css = getComputedStyle(el)
  const entries = Object.entries(PALETTE_TOKENS).map(([k, v]) => [k, css.getPropertyValue(v).trim()])
  return Object.fromEntries(entries) as unknown as HudPalette
}

/** Warna token + alfa (token berformat #rrggbb) untuk bayangan & area pijakan */
export function withAlpha(hex: string, alpha: number): string {
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex)
  if (!m) return hex
  const [r, g, b] = m.slice(1).map((h) => parseInt(h, 16))
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

export function computeFit(canvasW: number, canvasH: number, frameW: number, frameH: number): Fit {
  // Sebelum telemetri pertama dimensi bisa 0: pakai kanvas agar tidak membagi nol
  const fw = frameW > 0 ? frameW : canvasW || 1
  const fh = frameH > 0 ? frameH : canvasH || 1
  const scale = Math.min(canvasW / fw, canvasH / fh)
  const drawW = fw * scale
  const drawH = fh * scale
  return { scale, drawW, drawH, offsetX: (canvasW - drawW) / 2, offsetY: (canvasH - drawH) / 2 }
}

export function detectionStyle(d: Detection, palette: HudPalette): { color: string; label: string } {
  if (!d.is_inside_corridor) return { color: palette.outside, label: TEXT.outsideLane }
  if (d.is_full_body) return { color: palette.ok, label: TEXT.positionOk }
  return { color: palette.warn, label: TEXT.clip[d.clip_type] ?? TEXT.clipFallback }
}

export function drawHud(
  ctx: CanvasRenderingContext2D, w: number, h: number, t: Telemetry | null, guides: boolean, palette: HudPalette,
): void {
  ctx.clearRect(0, 0, w, h)
  if (!t) return
  const fit = computeFit(w, h, t.frame_width, t.frame_height)
  const { offsetX, offsetY, drawW, drawH, scale } = fit

  if (guides && t.zone?.enabled) {
    ctx.strokeStyle = palette.ok
    ctx.lineWidth = HUD.laneLineWidth
    ctx.setLineDash(HUD.laneDash)
    for (const y of [t.zone.y_min, t.zone.y_max]) {
      const lineY = offsetY + y * drawH
      ctx.beginPath()
      ctx.moveTo(offsetX, lineY)
      ctx.lineTo(offsetX + drawW, lineY)
      ctx.stroke()
    }
    ctx.setLineDash([])
  }


  if (guides && t.corridor?.enabled) {
    const x1 = offsetX + drawW * t.corridor.left_ratio
    const x2 = offsetX + drawW * t.corridor.right_ratio
    ctx.fillStyle = withAlpha(palette.background, HUD.shadeAlpha)
    ctx.fillRect(offsetX, offsetY, x1 - offsetX, drawH)
    ctx.fillRect(x2, offsetY, offsetX + drawW - x2, drawH)
    ctx.strokeStyle = palette.text
    ctx.lineWidth = HUD.laneLineWidth
    ctx.setLineDash(HUD.laneDash)
    for (const x of [x1, x2]) {
      ctx.beginPath()
      ctx.moveTo(x, offsetY)
      ctx.lineTo(x, offsetY + drawH)
      ctx.stroke()
    }
    // Area pijakan di dasar jalur
    const zoneW = (x2 - x1) * HUD.zoneWidthRatio
    const zoneH = Math.min(drawH * HUD.zoneHeightRatio, HUD.zoneMaxHeightPx)
    const zx = x1 + (x2 - x1 - zoneW) / 2
    const zy = offsetY + drawH - zoneH - HUD.zoneBottomGapPx
    ctx.strokeStyle = palette.ok
    ctx.strokeRect(zx, zy, zoneW, zoneH)
    ctx.setLineDash([])
    ctx.fillStyle = palette.ok
    ctx.font = `${HUD.zoneFont} ${palette.font}`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(TEXT.standHere, zx + zoneW / 2, zy + zoneH / 2)
    ctx.textAlign = 'left'
  }

  for (const d of t.detections ?? []) {
    const [bx1, by1, bx2, by2] = d.bbox
    const x = offsetX + bx1 * scale
    const y = offsetY + by1 * scale
    let { color, label } = detectionStyle(d, palette)
    if (t.zone?.enabled && !d.in_zone) {
      color = withAlpha(color, 0.4) // redup di luar zona
    }
    drawBrackets(ctx, x, y, (bx2 - bx1) * scale, (by2 - by1) * scale, color)
    if (d.is_inside_corridor && d.keypoints) {
      ctx.fillStyle = color
      for (const [kx, ky, conf] of d.keypoints) {
        if (conf >= t.keypoint_conf_threshold) {
          ctx.beginPath()
          ctx.arc(offsetX + kx * scale, offsetY + ky * scale, HUD.keypointRadiusPx, 0, Math.PI * 2)
          ctx.fill()
        }
      }
    }
    drawBadge(ctx, x, y, TEXT.badge(d.track_id, label), color, palette)
  }
}

function drawBrackets(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, color: string): void {
  const len = Math.min(w, h) * HUD.bracketRatio
  ctx.strokeStyle = color
  ctx.lineWidth = HUD.bracketLineWidth
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

function drawBadge(
  ctx: CanvasRenderingContext2D, x: number, y: number, text: string, color: string, palette: HudPalette,
): void {
  ctx.font = `${HUD.badgeFont} ${palette.font}`
  ctx.textBaseline = 'middle'
  const width = ctx.measureText(text).width + HUD.badgePaddingPx
  const top = Math.max(HUD.badgeHeightPx / 2, y - HUD.badgeHeightPx - HUD.badgeGapPx)
  ctx.fillStyle = withAlpha(palette.background, HUD.badgeAlpha)
  ctx.fillRect(x, top, width, HUD.badgeHeightPx)
  ctx.fillStyle = color
  ctx.fillRect(x, top, HUD.badgeStripePx, HUD.badgeHeightPx)
  ctx.fillStyle = palette.text
  ctx.fillText(text, x + HUD.badgeStripePx + HUD.badgePaddingPx / 2, top + HUD.badgeHeightPx / 2)
}
