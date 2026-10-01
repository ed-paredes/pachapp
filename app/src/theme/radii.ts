/** Radii follow hierarchy: small controls are tight, garment surfaces are the softest. */
export const radii = {
  /** Badges and small marks. */
  xs: 4,
  /** Season squares, calendar cells, inputs. */
  sm: 12,
  /** Cards and garment images. */
  md: 18,
  /** Large canvases and upload zones. */
  lg: 28,
  /** Chips, buttons, pills. */
  pill: 999,
  /** Garment plinth tiles. */
  tile: 14,
  /** Large panels. */
  panel: 20,
} as const;
