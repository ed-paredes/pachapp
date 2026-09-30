/** 4 dp spacing scale. */
export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

/** Content never grows wider than this on large screens. */
export const CONTENT_MAX_WIDTH = 1100;

/** Wardrobe cards never get narrower than this. */
export const MIN_CARD_WIDTH = 168;

/**
 * Number of grid columns that fit `availableWidth` with each card at least
 * `minCardWidth` wide, separated by `gap`. Always at least 1.
 */
export function gridColumns(
  availableWidth: number,
  minCardWidth: number = MIN_CARD_WIDTH,
  gap: number = spacing.md,
): number {
  return Math.max(1, Math.floor((availableWidth + gap) / (minCardWidth + gap)));
}
