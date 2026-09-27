import { describe, it, expect } from 'vitest';
import { isValidZoneBand, zoneLineY } from './zone';

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
});
