import { useQuery } from '@tanstack/react-query';

import { unwrap } from '@/api-client/errors';
import { apiClient } from '@/api-client/http-client';
import { queryKeys, type GarmentFilters } from '@/api-client/query-keys';

/** `GET /garments` with optional filters (category, status, needs_review, ...). */
export function useGarments(filters: GarmentFilters = {}) {
  return useQuery({
    queryKey: queryKeys.garments.list(filters),
    queryFn: async () => unwrap(await apiClient.GET('/garments', { params: { query: filters } })),
  });
}

/** `GET /garments/{id}`. Disabled while `id` is missing. */
export function useGarment(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.garments.detail(id ?? ''),
    enabled: !!id,
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/garments/{garment_id}', {
          params: { path: { garment_id: id as string } },
        }),
      ),
  });
}
