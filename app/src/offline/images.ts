import { Image } from 'expo-image';

import { imageUrl } from '@/lib/image-url';

import { offlineEnabled } from './persistence';

/** Images per `Image.prefetch` call: a failed batch only costs its own images. */
const PREFETCH_BATCH = 20;

type WithImages = { img_thumb: string | null; img_cutout: string | null };

/** Thumbnail and cutout URLs of the given garments, without repeats. */
export function garmentImageUrls(items: WithImages[]): string[] {
  const urls = new Set<string>();
  for (const item of items) {
    for (const path of [item.img_thumb, item.img_cutout]) {
      const url = imageUrl(path);
      if (url) urls.add(url);
    }
  }
  return [...urls];
}

/**
 * Downloads the images that are not on disk yet into expo-image's disk cache, the same cache the
 * garment components read (`GARMENT_IMAGE_CACHE_POLICY`), so they render with the backend stopped.
 * Images already cached are skipped, which also re-downloads any the OS evicted. Native only; it
 * never throws, and returns how many images could not be fetched.
 */
export async function prefetchGarmentImages(urls: string[]): Promise<number> {
  if (!offlineEnabled()) return 0;
  const missing: string[] = [];
  for (const url of urls) {
    try {
      if (!(await Image.getCachePathAsync(url))) missing.push(url);
    } catch {
      missing.push(url);
    }
  }
  let failed = 0;
  for (let start = 0; start < missing.length; start += PREFETCH_BATCH) {
    const batch = missing.slice(start, start + PREFETCH_BATCH);
    try {
      if (!(await Image.prefetch(batch, 'disk'))) failed += batch.length;
    } catch {
      failed += batch.length;
    }
  }
  return failed;
}
