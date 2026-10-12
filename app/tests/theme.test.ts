import { colors, gridColumns, MIN_GRID_COLUMNS, tint } from '@/theme';

function luminance(hex: string): number {
  const n = parseInt(hex.slice(1), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
    const c = v / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe('tint', () => {
  it('mixes 16 % of the colour into the tint base by default', () => {
    // 0.84 * 0xF1 = 202.4, 0.84 * 0xEC = 198.2, 0.84 * 0xE4 = 191.5 (rounded half up)
    expect(tint('#000000')).toBe('rgb(202, 198, 192)');
  });

  it('returns the colour itself at amount 1 and the base at amount 0', () => {
    expect(tint('#B5562F', 1)).toBe('rgb(181, 86, 47)');
    expect(tint('#B5562F', 0)).toBe('rgb(241, 236, 228)');
  });

  it('accepts a custom base and short or unprefixed hex values', () => {
    expect(tint('#FFFFFF', 0.5, '#000000')).toBe('rgb(128, 128, 128)');
    expect(tint('ffffff', 0.5, '000000')).toBe('rgb(128, 128, 128)');
  });

  it('expands 3-digit hex by doubling each digit', () => {
    expect(tint('#abc', 1)).toBe(tint('#aabbcc', 1));
    expect(tint('abc', 1)).toBe('rgb(170, 187, 204)');
    expect(tint('#fff', 0.5, '#000')).toBe('rgb(128, 128, 128)');
  });

  it('expands 4-digit hex like CSS and drops the alpha, as for 8 digits', () => {
    expect(tint('#abcd', 1)).toBe('rgb(170, 187, 204)');
    expect(tint('#abcd', 1)).toBe(tint('#aabbccdd', 1));
  });
});

describe('gridColumns', () => {
  it('never drops below two columns, even on a narrow phone', () => {
    expect(gridColumns(200)).toBe(MIN_GRID_COLUMNS);
    expect(gridColumns(358)).toBe(2);
  });

  it('fits roughly one column per 190 dp plus the gap', () => {
    expect(gridColumns(1088, undefined, 12)).toBe(5);
    expect(gridColumns(800, undefined, 12)).toBe(4);
    expect(gridColumns(1200, undefined, 12)).toBe(6);
  });

  it('uses two columns on a phone width and keeps the floor for degenerate widths', () => {
    expect(gridColumns(390 - 32, undefined, 12)).toBe(2);
    expect(gridColumns(0)).toBe(MIN_GRID_COLUMNS);
    expect(gridColumns(-50)).toBe(MIN_GRID_COLUMNS);
  });
});

describe('colour contrast (WCAG AA)', () => {
  const backgrounds = [colors.bg, colors.surface] as const;

  it.each(['ink', 'ink2', 'ink3Text', 'accentText', 'danger'] as const)(
    'text colour %s reaches 4.5:1 on bg and surface',
    (token) => {
      for (const bg of backgrounds) expect(contrast(colors[token], bg)).toBeGreaterThanOrEqual(4.5);
    },
  );

  it('keeps counters and secondary text legible on the sand fill', () => {
    expect(contrast(colors.ink3Text, colors.surface2)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(colors.ink2, colors.surface2)).toBeGreaterThanOrEqual(4.5);
  });

  it.each([
    ['okText', 'okSoft'],
    ['infoText', 'infoSoft'],
    ['warnText', 'warnSoft'],
    ['accentText', 'accentSoft'],
    ['danger', 'dangerSoft'],
  ] as const)('%s reaches 4.5:1 on %s', (fg, bg) => {
    expect(contrast(colors[fg], colors[bg])).toBeGreaterThanOrEqual(4.5);
  });

  it('lineStrong reaches 3:1 as a boundary against bg, surface and surface2', () => {
    for (const bg of [colors.bg, colors.surface, colors.surface2]) {
      expect(contrast(colors.lineStrong, bg)).toBeGreaterThanOrEqual(3);
    }
  });

  it('white text on the accent and ink fills reaches 4.5:1', () => {
    expect(contrast(colors.onInk, colors.accent)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(colors.onInk, colors.ink)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(colors.navInactive, colors.ink)).toBeGreaterThanOrEqual(4.5);
  });

  it('documents why the raw mockup tones are decorative only', () => {
    expect(contrast(colors.ink3, colors.bg)).toBeLessThan(3);
    expect(contrast(colors.line, colors.bg)).toBeLessThan(3);
  });
});
