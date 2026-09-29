import { useQuery } from '@tanstack/react-query';

import { apiClient } from '@/api-client/http-client';

/**
 * `GET /health`, the one real endpoint wired up in this iteration (see
 * `docs/specs/07-app-ui.md`, "Uso del cliente de API vía TanStack Query").
 * Shown as a discreet connection status line in Ajustes.
 */
export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: async () => {
      const { data, error, response } = await apiClient.GET('/health');
      if (!response.ok || error) {
        throw new Error(`Health check failed with status ${response.status}`);
      }
      return data;
    },
  });
}
