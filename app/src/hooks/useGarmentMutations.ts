import { useMutation, useQueryClient, type QueryClient } from '@tanstack/react-query';

import { unwrap } from '@/api-client/errors';
import { apiClient } from '@/api-client/http-client';
import { queryKeys } from '@/api-client/query-keys';
import type { components } from '@/api-client/schema';

export type GarmentPatch = components['schemas']['GarmentPatch'];

/** UI-REQ-016: refresh the Armario lists and this garment's detail. */
function invalidateGarment(queryClient: QueryClient, id: string) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.garments.lists() }),
    queryClient.invalidateQueries({ queryKey: queryKeys.garments.detail(id) }),
  ]);
}

/** `PATCH /garments/{id}`. */
export function usePatchGarment(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (patch: GarmentPatch) =>
      unwrap(
        await apiClient.PATCH('/garments/{garment_id}', {
          params: { path: { garment_id: id } },
          body: patch,
        }),
      ),
    onSuccess: () => invalidateGarment(queryClient, id),
  });
}

/** `POST /garments/{id}/review/complete` (the "Revisión terminada" button). */
export function useCompleteReview(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await apiClient.POST('/garments/{garment_id}/review/complete', {
          params: { path: { garment_id: id } },
        }),
      ),
    onSuccess: () => invalidateGarment(queryClient, id),
  });
}

/**
 * `POST /garments/{id}/retry`. Also invalidates the job queries so a stopped
 * poll of the failed job restarts against the requeued job.
 */
export function useRetryGarment(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await apiClient.POST('/garments/{garment_id}/retry', {
          params: { path: { garment_id: id } },
        }),
      ),
    onSuccess: () =>
      Promise.all([
        invalidateGarment(queryClient, id),
        queryClient.invalidateQueries({ queryKey: queryKeys.jobs.all }),
      ]),
  });
}

/** `POST /garments/{id}/archive`. */
export function useArchiveGarment(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await apiClient.POST('/garments/{garment_id}/archive', {
          params: { path: { garment_id: id } },
        }),
      ),
    onSuccess: () => invalidateGarment(queryClient, id),
  });
}

/** `POST /garments/{id}/reactivate`. */
export function useReactivateGarment(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await apiClient.POST('/garments/{garment_id}/reactivate', {
          params: { path: { garment_id: id } },
        }),
      ),
    onSuccess: () => invalidateGarment(queryClient, id),
  });
}

/** `DELETE /garments/{id}`; the detail query is dropped instead of refetched. */
export function useDeleteGarment(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await apiClient.DELETE('/garments/{garment_id}', {
          params: { path: { garment_id: id } },
        }),
      ),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: queryKeys.garments.detail(id) });
      return queryClient.invalidateQueries({ queryKey: queryKeys.garments.lists() });
    },
  });
}
