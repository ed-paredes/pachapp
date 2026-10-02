/** Radii follow hierarchy: small controls are tight, garment surfaces are the softest. */
export const radii = {
  /** Badges and small marks. */
  xs: 4,
  /** Buttons, inputs. */
  sm: 8,
  /** Chips. */
  pill: 999,
  /** Garment plinth tiles. */
  tile: 14,
  /** Large panels. */
  panel: 20,
} as const;
