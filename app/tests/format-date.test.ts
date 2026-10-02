import { formatLastWorn } from '@/lib/format-date';

const now = new Date(2026, 9, 1, 15, 0); // 1 Oct 2026

describe('formatLastWorn', () => {
  it('says "Nunca" when the garment was never worn', () => {
    expect(formatLastWorn(null, now)).toBe('Nunca');
  });

  it('uses relative words for today, yesterday and recent days', () => {
    expect(formatLastWorn(new Date(2026, 9, 1, 8).toISOString(), now)).toBe('Hoy');
    expect(formatLastWorn(new Date(2026, 8, 30, 22).toISOString(), now)).toBe('Ayer');
    expect(formatLastWorn(new Date(2026, 8, 19, 12).toISOString(), now)).toBe('Hace 12 d');
  });

  it('switches to a short date after two months', () => {
    expect(formatLastWorn(new Date(2026, 2, 12, 12).toISOString(), now)).toBe('12 mar');
    expect(formatLastWorn(new Date(2025, 2, 12, 12).toISOString(), now)).toBe('mar 2025');
  });

  it('returns unparseable input unchanged', () => {
    expect(formatLastWorn('not a date', now)).toBe('not a date');
  });
});
