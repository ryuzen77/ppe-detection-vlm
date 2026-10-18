import { describe, it, expect } from 'vitest';
import { isValidZoneBand, zoneLineY, ratioToPercent, percentToRatio } from './zone';

describe('zone module', () => {
  it('isValidZoneBand', () => {
    expect(isValidZoneBand(0.7, 0.85, 0.04)).toBe(true);
    expect(isValidZoneBand(0.85, 0.7, 0.04)).toBe(false);
    expect(isValidZoneBand(0.7, 0.72, 0.04)).toBe(false);
    expect(isValidZoneBand(-0.1, 0.5, 0.04)).toBe(false);
    expect(isValidZoneBand(0.5, 1.2, 0.04)).toBe(false);
  });

  it('zoneLineY computes correctly', () => {
    expect(zoneLineY(0.5, 10, 200)).toBe(110);
  });

  it('ratioToPercent dan percentToRatio konversi timbal balik dengan benar', () => {
    expect(ratioToPercent(0.7)).toBe(70);
    expect(ratioToPercent(0.85)).toBe(85);
    expect(ratioToPercent(0)).toBe(0);
    expect(ratioToPercent(1)).toBe(100);

    expect(percentToRatio(70)).toBe(0.7);
    expect(percentToRatio(85)).toBe(0.85);
    expect(percentToRatio(100)).toBe(1);
    expect(percentToRatio(-5)).toBe(0);
    expect(percentToRatio(120)).toBe(1);
    expect(percentToRatio(37.6)).toBe(0.38);
    expect(percentToRatio(37.4)).toBe(0.37);
  });
});
