import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { unwrap } from '@/api-client/errors';
import { apiClient } from '@/api-client/http-client';
import { queryKeys } from '@/api-client/query-keys';
import type { components } from '@/api-client/schema';

export type SettingsPatch = components['schemas']['SettingsPatch'];

/** One `GET /settings` request; shared by the hook and the offline sync. */
export async function fetchSettings() {
  return unwrap(await apiClient.GET('/settings'));
}

/** `GET /settings`. */
export function useSettings() {
  return useQuery({
    queryKey: queryKeys.settings,
    queryFn: fetchSettings,
  });
}

/** `PATCH /settings`; a 400 `INVALID_WEIGHTS` surfaces as `ApiError`. */
export function usePatchSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (patch: SettingsPatch) =>
      unwrap(await apiClient.PATCH('/settings', { body: patch })),
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.settings, data);
      return queryClient.invalidateQueries({ queryKey: queryKeys.settings });
    },
  });
}
