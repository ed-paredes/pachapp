/**
 * "Probador" palette, redesign edition: linen room, white cards, ink action, terracotta accent.
 *
 * Surfaces keep the mockup values. The raw mockup tones that fail WCAG AA as text or as a
 * control boundary keep their name for decorative use, and each has an AA-safe sibling for the
 * jobs that need it (contrast ratios computed with the WCAG 2.x relative-luminance formula):
 *
 * - `ink3` #A39A8E is 2.51:1 on bg: placeholder icons and decoration only. Text uses `ink3Text`
 *   #6F665B (5.1:1 on bg, 4.7:1 on surface2).
 * - `accent` #B5562F is 4.37:1 on bg: fills (buttons, dots) only. Small accent text uses
 *   `accentText` #A24D2A (5.2:1 on bg, 4.6:1 on accentSoft). White on `accent` is 4.84:1.
 * - `ok`, `info`, `warn` on their soft fills are 4.13:1 / 4.3:1 / 3.52:1: pill text uses
 *   `okText` #3F6649 (5.5:1 on okSoft), `infoText` #33607A (5.6:1 on infoSoft) and `warnText`
 *   #7F5614 (5.5:1 on warnSoft).
 * - `line` #E4DDD2 is 1.22:1 on bg: decorative dividers only. Boundaries of inputs and chips
 *   (WCAG 1.4.11, 3:1) use `lineStrong` #8C8377 (3.4:1 on bg, 3.7:1 on surface, 3.1:1 on surface2).
 */
export const colors = {
  /** Screen background (linen). */
  bg: '#F6F3EE',
  /** Cards. */
  surface: '#FFFFFF',
  /** Sand: chips, meter tracks, secondary buttons. */
  surface2: '#EFEAE2',
  surface3: '#E7E0D5',
  /** Primary text, primary button, floating nav. */
  ink: '#1F1B16',
  /** Secondary text (5.3:1 on bg). */
  ink2: '#6B6359',
  /** Decorative tone only; see `ink3Text` for text. */
  ink3: '#A39A8E',
  /** Placeholders and counters as text (AA). */
  ink3Text: '#6F665B',
  /** Decorative dividers. */
  line: '#E4DDD2',
  /** Input and chip boundaries (>= 3:1). */
  lineStrong: '#8C8377',
  /** Terracotta fills. */
  accent: '#B5562F',
  accentSoft: '#F4E3D9',
  /** Accent as small text (AA). */
  accentText: '#A24D2A',
  ok: '#4F7A5A',
  okSoft: '#E3EEE5',
  okText: '#3F6649',
  info: '#3E6A8A',
  infoSoft: '#E1EBF2',
  infoText: '#33607A',
  warn: '#A3741F',
  warnSoft: '#F6ECD6',
  warnText: '#7F5614',
  danger: '#B23A30',
  dangerSoft: '#F6E7E4',
  /** Base the garment tint is mixed into. */
  tintBase: '#F1ECE4',
  /** Text on ink and accent fills. */
  onInk: '#FFFFFF',
  /** Inactive icon on the dark nav (10:1 on ink). */
  navInactive: '#CFC6BA',

  // Aliases kept for screens not yet migrated; they follow the new palette.
  stone: '#F6F3EE',
  plinth: '#FFFFFF',
  charcoal: '#1F1B16',
  muted: '#6B6359',
  hairline: '#E4DDD2',
  /** The primary action is ink now. */
  olive: '#1F1B16',
  onOlive: '#FFFFFF',
  brass: '#F6ECD6',
  /** Text on brass fills (5.5:1). */
  onBrass: '#7F5614',
  error: '#B23A30',
  errorSurface: '#F6E7E4',
} as const;

export type ColorToken = keyof typeof colors;
