import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';

import { unwrap } from '@/api-client/errors';
import { apiClient } from '@/api-client/http-client';
import { queryKeys } from '@/api-client/query-keys';
import type { components } from '@/api-client/schema';

export type SettingsPatch = components['schemas']['SettingsPatch'];
export type SettingsRead = components['schemas']['SettingsRead'];

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
      const before = queryClient.getQueryData<SettingsRead>(queryKeys.settings);
      queryClient.setQueryData(queryKeys.settings, data);
      if (before) followModelChange(queryClient, before, data);
      return queryClient.invalidateQueries({ queryKey: queryKeys.settings });
    },
  });
}

/**
 * Hoy follows the try-on model the owner picks in Ajustes:
 * - a new skin tone changes only the image served for a finished render (`GET /tryon/{id}` returns
 *   the variant of the stored tone), so the saved render reads are refetched;
 * - a new gender is another base, hence another render: the look -> render links are dropped, so
 *   every look is untried again and "Verlo puesto" requests it for the new base (the server answers
 *   at once when that render already exists).
 */
function followModelChange(queryClient: QueryClient, before: SettingsRead, after: SettingsRead) {
  if (before.tryon_gender !== after.tryon_gender) {
    void queryClient.resetQueries({ queryKey: queryKeys.tryon.byLooks() });
  }
  if (before.tryon_skin_tone !== after.tryon_skin_tone) {
    void queryClient.invalidateQueries({ queryKey: queryKeys.tryon.details() });
  }
}
