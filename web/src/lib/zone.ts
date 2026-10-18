/** Pita zona sah: 0 ≤ yMin < yMax ≤ 1 dan selisih ≥ minHeight. */
export function isValidZoneBand(yMin: number, yMax: number, minHeight: number): boolean {
  return yMin >= 0 && yMax <= 1 && yMin < yMax && (yMax - yMin) >= minHeight;
}

/** Posisi y relatif (0–1) -> piksel kanvas, memakai hasil computeFit dari hud.ts. */
export function zoneLineY(y: number, offsetY: number, drawH: number): number {
  return offsetY + (y * drawH);
}

/** Konversi rasio 0..1 ke persentase bulat (0..100) untuk label operator */
export function ratioToPercent(ratio: number): number {
  return Math.round(ratio * 100);
}

/** Konversi persentase 0..100 ke rasio desimal 0..1 */
export function percentToRatio(percent: number): number {
  const clamped = Math.max(0, Math.min(100, Number.isFinite(percent) ? percent : 0));
  return Math.round(clamped) / 100;
}

