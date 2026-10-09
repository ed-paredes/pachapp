import { useQuery } from '@tanstack/react-query';

import { unwrap } from '@/api-client/errors';
import { apiClient } from '@/api-client/http-client';
import { queryKeys } from '@/api-client/query-keys';
import type { components } from '@/api-client/schema';
import type { LookRole } from '@/components/today/types';

export type TryOnCapabilities = components['schemas']['TryOnCapabilities'];

/** The flag and the categories change with the backend config, not while the app runs. */
export const CAPABILITIES_STALE_MS = 24 * 60 * 60 * 1000;

/** One `GET /tryon/capabilities` request. */
export async function fetchTryOnCapabilities() {
  return unwrap(await apiClient.GET('/tryon/capabilities'));
}

/**
 * `GET /tryon/capabilities`. Persisted on native, so the button state is known offline; the saved
 * copy is refreshed once a day.
 */
export function useTryOnCapabilities() {
  return useQuery({
    queryKey: queryKeys.tryon.capabilities,
    queryFn: fetchTryOnCapabilities,
    staleTime: CAPABILITIES_STALE_MS,
  });
}

/** True when try-on is enabled and at least one piece of the look is a supported category. */
export function isLookTryable(
  pieces: { role: LookRole }[],
  capabilities: TryOnCapabilities | undefined,
): boolean {
  if (!capabilities?.enabled) return false;
  return pieces.some((piece) => capabilities.supported_categories.includes(piece.role));
}
