/** Soft elevations as `boxShadow` strings (React Native >= 0.76, also on web). */
export const shadows = {
  /** Cards. */
  card: '0px 1px 2px rgba(31,27,22,0.04), 0px 8px 24px rgba(31,27,22,0.06)',
  /** Floating elements: tab bar, toast. */
  raised: '0px 2px 4px rgba(31,27,22,0.05), 0px 20px 50px rgba(31,27,22,0.12)',
  /** Active segment of a `Segmented`. */
  segment: '0px 1px 3px rgba(0,0,0,0.08)',
} as const;
