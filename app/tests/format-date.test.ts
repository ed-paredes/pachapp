import { formatLastWorn, formatToday, greeting } from '@/lib/format-date';

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

describe('formatToday and greeting', () => {
  it('writes the capitalised es-ES date', () => {
    expect(formatToday(new Date(2026, 9, 1))).toBe('Jueves, 1 de octubre');
    expect(formatToday(new Date(2026, 2, 8))).toBe('Domingo, 8 de marzo');
  });

  it('greets by time of day', () => {
    expect(greeting(new Date(2026, 9, 1, 8))).toBe('Buenos días');
    expect(greeting(new Date(2026, 9, 1, 12))).toBe('Buenas tardes');
    expect(greeting(new Date(2026, 9, 1, 19, 59))).toBe('Buenas tardes');
    expect(greeting(new Date(2026, 9, 1, 22))).toBe('Buenas noches');
    expect(greeting(new Date(2026, 9, 1, 3))).toBe('Buenas noches');
  });
});
