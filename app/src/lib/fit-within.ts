export type Size = { width: number; height: number };

/**
 * Largest size with the intrinsic aspect ratio that fits inside `max`.
 * Never upscales: a small image keeps its intrinsic size instead of being blurred.
 */
export function fitWithin(intrinsic: Size, max: Size): Size {
  if (intrinsic.width <= 0 || intrinsic.height <= 0 || max.width <= 0 || max.height <= 0) {
    return { width: 0, height: 0 };
  }
  const scale = Math.min(max.width / intrinsic.width, max.height / intrinsic.height, 1);
  return {
    width: Math.round(intrinsic.width * scale),
    height: Math.round(intrinsic.height * scale),
  };
}
