/** 4 dp spacing scale. */
export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 28,
  /** Side margin of a screen. */
  screen: 16,
} as const;

/** Content never grows wider than this on large screens. */
export const CONTENT_MAX_WIDTH = 1120;

/** From this window width Hoy and Detalle switch to two columns. */
export const TWO_COLUMNS = 880;

/** Wardrobe cards aim at this width (the grid shows `width / 190` columns). */
export const MIN_CARD_WIDTH = 190;

/** The wardrobe grid never drops below this many columns, even on narrow phones. */
export const MIN_GRID_COLUMNS = 2;

/**
 * Number of grid columns that fit `availableWidth` with each card about
 * `minCardWidth` wide, separated by `gap`. Always at least `MIN_GRID_COLUMNS`.
 */
export function gridColumns(
  availableWidth: number,
  minCardWidth: number = MIN_CARD_WIDTH,
  gap: number = spacing.md,
): number {
  return Math.max(MIN_GRID_COLUMNS, Math.floor((availableWidth + gap) / (minCardWidth + gap)));
}
