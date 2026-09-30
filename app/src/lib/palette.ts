import type { components } from '@/api-client/schema';

export type ColorEntry = components['schemas']['ColorEntry'];

/** Fixed colour palette (ING-REQ-012). Mirrors `backend/src/worker/colors.py::PALETTE`. */
export const PALETTE: Record<string, [number, number, number]> = {
  negro: [25, 25, 28],
  blanco: [245, 245, 243],
  gris: [128, 128, 128],
  beige: [222, 205, 175],
  camel: [193, 154, 107],
  marino: [20, 30, 80],
  denim: [65, 95, 145],
  marrón: [110, 70, 40],
  rojo: [200, 30, 40],
  burdeos: [110, 20, 40],
  rosa: [240, 150, 180],
  naranja: [240, 130, 30],
  amarillo: [245, 210, 40],
  verde: [40, 150, 70],
  oliva: [110, 110, 40],
  azul: [30, 90, 220],
  celeste: [135, 200, 235],
  morado: [120, 60, 160],
  turquesa: [40, 190, 180],
  caqui: [175, 165, 110],
};

export const PALETTE_NAMES = Object.keys(PALETTE);

/** Most colours a garment can carry when edited by hand (the extractor uses k=4). */
export const MAX_COLORS = 4;

const WHITE_D65 = [0.95047, 1.0, 1.08883];

function linear(channel: number): number {
  const c = channel / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function labF(t: number): number {
  return t > 216 / 24389 ? Math.cbrt(t) : (24389 / 27 / 116) * t + 16 / 116;
}

/** sRGB (0-255) to CIELAB, D65; same convention as the backend colour step. */
export function rgbToLab([r, g, b]: [number, number, number]): [number, number, number] {
  const lr = linear(r);
  const lg = linear(g);
  const lb = linear(b);
  const x = (0.4124564 * lr + 0.3575761 * lg + 0.1804375 * lb) / WHITE_D65[0];
  const y = (0.2126729 * lr + 0.7151522 * lg + 0.072175 * lb) / WHITE_D65[1];
  const z = (0.0193339 * lr + 0.119192 * lg + 0.9503041 * lb) / WHITE_D65[2];
  const fx = labF(x);
  const fy = labF(y);
  const fz = labF(z);
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

export function paletteHex(name: string): string {
  const rgb = PALETTE[name] ?? [128, 128, 128];
  return `#${rgb.map((v) => v.toString(16).padStart(2, '0')).join('')}`;
}

const PROPORTION_DECIMALS = 10000;
const MIN_NEW_WEIGHT = 0.1;

/**
 * Builds the `colors` PATCH body for a hand-edited list of palette names
 * (dominant first as ordered by the user).
 *
 * Proportions: names that were already present keep their previous
 * proportion; new names share what is left (`1 - kept`, at least
 * `MIN_NEW_WEIGHT` each) evenly. Weights are then normalised to sum 1, floored
 * to 4 decimals (so the sum never exceeds 1) and sorted descending (stable, so
 * ties keep the user's order), as the API requires (ING-REQ-011).
 */
export function buildColors(names: string[], previous: ColorEntry[] | null): ColorEntry[] {
  const before = new Map((previous ?? []).map((entry) => [entry.name, entry.proportion]));
  const kept = names.filter((name) => before.has(name));
  const added = names.filter((name) => !before.has(name));
  const keptSum = kept.reduce((sum, name) => sum + (before.get(name) ?? 0), 0);
  const newWeight = added.length ? Math.max((1 - keptSum) / added.length, MIN_NEW_WEIGHT) : 0;
  const weights = names.map((name) => before.get(name) ?? newWeight);
  const total = weights.reduce((sum, w) => sum + w, 0) || 1;

  return names
    .map((name, index) => {
      const rgb = PALETTE[name];
      return {
        name,
        hex: paletteHex(name),
        lab: rgbToLab(rgb),
        proportion:
          Math.floor((weights[index] / total) * PROPORTION_DECIMALS) / PROPORTION_DECIMALS,
        index,
      };
    })
    .sort((a, b) => b.proportion - a.proportion || a.index - b.index)
    .map(({ index: _index, ...entry }) => entry);
}
