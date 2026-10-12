import { fitWithin, type Size } from '@/lib/fit-within';

/** Hero image is at most this share of the window height. */
export const HERO_MAX_HEIGHT_RATIO = 0.45;
/** Hero image is at most this wide (dp). */
export const HERO_MAX_WIDTH = 520;

type HeroBoxInput = {
  /** The uri being shown now. */
  uri: string;
  /** Intrinsic size reported by the last load, with the uri it belongs to. */
  loaded: { uri: string; size: Size } | null;
  panelWidth: number;
  /** Padding on each side of the image inside the panel. */
  padding: number;
  windowHeight: number;
  maxHeightRatio?: number;
};

/**
 * Size to render the hero image at: inside 45 % of the window height and 520 dp (less when the
 * panel is narrower), never above the intrinsic size. A size loaded for another uri is ignored so
 * a swapped image does not reuse the previous one's proportions; until the size is known the
 * largest allowed box is reserved.
 */
export function heroImageBox({
  uri,
  loaded,
  panelWidth,
  padding,
  windowHeight,
  maxHeightRatio = HERO_MAX_HEIGHT_RATIO,
}: HeroBoxInput): Size {
  const max: Size = {
    width: Math.min(HERO_MAX_WIDTH, Math.max(0, panelWidth - padding * 2)),
    height: Math.round(windowHeight * maxHeightRatio),
  };
  const intrinsic = loaded?.uri === uri ? loaded.size : null;
  return intrinsic ? fitWithin(intrinsic, max) : max;
}
