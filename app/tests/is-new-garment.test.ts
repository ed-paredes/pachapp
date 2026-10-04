import { isNewGarment, NEW_WINDOW_MS } from '@/components/GarmentCard';

const NOW = Date.parse('2026-10-03T12:00:00Z');
const at = (offsetMs: number, wear_count = 0) => ({
  wear_count,
  created_at: new Date(NOW + offsetMs).toISOString(),
});

describe('isNewGarment', () => {
  it('is new while unworn and inside the window', () => {
    expect(isNewGarment(at(-1000), NOW)).toBe(true);
    expect(isNewGarment(at(-NEW_WINDOW_MS), NOW)).toBe(true);
  });

  it('is not new once worn or older than the window', () => {
    expect(isNewGarment(at(-1000, 1), NOW)).toBe(false);
    expect(isNewGarment(at(-NEW_WINDOW_MS - 1), NOW)).toBe(false);
  });

  it('tolerates small clock skew but not far-future timestamps', () => {
    expect(isNewGarment(at(60_000), NOW)).toBe(true);
    expect(isNewGarment(at(NEW_WINDOW_MS + 1), NOW)).toBe(false);
  });

  it('is not new for an unparseable timestamp', () => {
    expect(isNewGarment({ wear_count: 0, created_at: 'nope' }, NOW)).toBe(false);
  });
});
