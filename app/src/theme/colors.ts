/** "Probador" palette: stone room, plinth surfaces, olive action, brass marks. */
export const colors = {
  /** App background. */
  stone: '#E9EAE6',
  /** Garment surfaces and cards. */
  plinth: '#FBFBF9',
  /** Primary action and selection. */
  olive: '#4B5B3C',
  /** Text on olive surfaces. */
  onOlive: '#FBFBF9',
  /** Needs-review marks; use sparingly. */
  brass: '#B08D57',
  /** Text on brass surfaces (AA contrast). */
  onBrass: '#2B2B2B',
  /** Body text. */
  charcoal: '#2B2B2B',
  /** Secondary text. */
  muted: '#6B6E68',
  /** Borders and dividers. */
  hairline: '#D9DAD5',
  error: '#A3362B',
  errorSurface: '#F6E7E4',
} as const;

export type ColorToken = keyof typeof colors;
