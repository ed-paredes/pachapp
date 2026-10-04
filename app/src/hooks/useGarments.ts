import { useInfiniteQuery, useQuery } from '@tanstack/react-query';

import { unwrap } from '@/api-client/errors';
import { apiClient } from '@/api-client/http-client';
import { queryKeys, type GarmentFilters } from '@/api-client/query-keys';

/** One `GET /garments` request; shared by the hooks and the offline sync. */
export async function fetchGarmentList(filters: GarmentFilters) {
  return unwrap(await apiClient.GET('/garments', { params: { query: filters } }));
}

/** One `GET /garments/{id}` request; shared by the hook and the offline sync. */
export async function fetchGarmentDetail(id: string) {
  return unwrap(
    await apiClient.GET('/garments/{garment_id}', { params: { path: { garment_id: id } } }),
  );
}

/** `GET /garments` with optional filters (category, status, needs_review, ...). */
export function useGarments(filters: GarmentFilters = {}) {
  return useQuery({
    queryKey: queryKeys.garments.list(filters),
    queryFn: () => fetchGarmentList(filters),
  });
}

/**
 * Flattens loaded pages into one list, dropping repeated garment ids (first
 * occurrence wins): offset pagination can return the same garment on two pages
 * when garments are created between page requests.
 */
export function flattenGarmentPages<T extends { id: string }>(
  pages: { items: T[] }[] | undefined,
): T[] {
  const seen = new Set<string>();
  const result: T[] = [];
  for (const page of pages ?? []) {
    for (const item of page.items) {
      if (seen.has(item.id)) continue;
      seen.add(item.id);
      result.push(item);
    }
  }
  return result;
}

/** Job states in which the worker still owns the garment (list should keep polling). */
const ACTIVE_JOB_STATUSES = ['pending', 'claimed', 'running'];

/** Armario polls the list every 2 s while any garment is still processing. */
export const GARMENTS_POLL_INTERVAL_MS = 2000;

/** Next `page` param of the infinite garment list, or `undefined` once everything is loaded. */
export function nextGarmentPage(
  last: { items: unknown[]; total: number; page: number },
  pages: { items: unknown[] }[],
): number | undefined {
  const loaded = pages.reduce((count, page) => count + page.items.length, 0);
  return last.items.length > 0 && loaded < last.total ? last.page + 1 : undefined;
}

/**
 * `GET /garments` as an infinite list (Armario): `filters.page` is driven by the
 * query, later pages come from `fetchNextPage`. While any loaded item's job is
 * pending/claimed/running the list is refetched every 2 s, so thumbnails and
 * progress appear without a manual refresh; polling stops on its own.
 */
export function useInfiniteGarments(filters: Omit<GarmentFilters, 'page'> = {}) {
  return useInfiniteQuery({
    queryKey: queryKeys.garments.infinite(filters),
    initialPageParam: 1,
    queryFn: ({ pageParam }) => fetchGarmentList({ ...filters, page: pageParam }),
    getNextPageParam: nextGarmentPage,
    refetchInterval: (query) => {
      const processing = query.state.data?.pages.some((page) =>
        page.items.some((item) => item.job && ACTIVE_JOB_STATUSES.includes(item.job.status)),
      );
      return processing ? GARMENTS_POLL_INTERVAL_MS : false;
    },
  });
}

/** `GET /garments/{id}`. Disabled while `id` is missing. */
export function useGarment(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.garments.detail(id ?? ''),
    enabled: !!id,
    queryFn: () => fetchGarmentDetail(id as string),
  });
}
