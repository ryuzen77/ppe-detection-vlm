/** Pita zona sah: 0 ≤ yMin < yMax ≤ 1 dan selisih ≥ minHeight. */
export function isValidZoneBand(yMin: number, yMax: number, minHeight: number): boolean {
  return yMin >= 0 && yMax <= 1 && yMin < yMax && (yMax - yMin) >= minHeight;
}

/** Posisi y relatif (0–1) -> piksel kanvas, memakai hasil computeFit dari hud.ts. */
export function zoneLineY(y: number, offsetY: number, drawH: number): number {
  return offsetY + (y * drawH);
}
