import { API_BASE_URL } from '@/api-client/config';

/**
 * Absolute URL of a stored image. The API returns relative paths
 * (`cutout/{id}.png`, API-REQ-016) served under `/images`.
 */
export function imageUrl(relativePath: string | null | undefined): string | null {
  if (!relativePath) {
    return null;
  }
  const base = API_BASE_URL.replace(/\/+$/, '');
  return `${base}/images/${relativePath.replace(/^\/+/, '')}`;
}

/**
 * Cache policy of every garment image. `memory-disk` keeps the file on disk, which is what lets
 * native show the wardrobe with the backend stopped (the sync fills it, see `offline/images.ts`).
 */
export const GARMENT_IMAGE_CACHE_POLICY = 'memory-disk' as const;
