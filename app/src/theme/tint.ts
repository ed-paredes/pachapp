import { colors } from './colors';

function parse(hex: string): [number, number, number] {
  const digits = hex.replace('#', '');
  // Short forms (#abc, #abcd) double each digit, as CSS does; any alpha is dropped below.
  const full =
    digits.length === 3 || digits.length === 4 ? [...digits].map((d) => d + d).join('') : digits;
  const n = parseInt(full.padEnd(6, '0').slice(0, 6), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/**
 * Background tinted for a garment: mixes its dominant colour with `tintBase`.
 * Replaces the mockup's CSS `color-mix(in srgb, <color> 16%, #F1ECE4)`.
 */
export function tint(hex: string, amount = 0.16, base: string = colors.tintBase): string {
  const [r1, g1, b1] = parse(hex);
  const [r2, g2, b2] = parse(base);
  const mix = (a: number, b: number) => Math.round(a * amount + b * (1 - amount));
  return `rgb(${mix(r1, r2)}, ${mix(g1, g2)}, ${mix(b1, b2)})`;
}
