import { QueryClient } from '@tanstack/react-query';

import { applyPersistedDefaults, offlineEnabled } from '@/offline/persistence';

/**
 * How long fetched data counts as fresh. With TanStack's default of 0 every mounted query of
 * every tab is stale at once, so a window focus (web) or a reconnect refetched all of them in
 * one burst (~23 requests). Mutations still refresh what they touch: `invalidateQueries` marks
 * queries stale regardless of this window, and polling (`refetchInterval`) ignores it.
 */
export const DEFAULT_STALE_TIME_MS = 30_000;

/**
 * Shared TanStack Query client. Automatic retries are disabled: every
 * screen that depends on a network request surfaces its own explicit
 * error-with-retry state (UI-REQ-008), so a silent internal retry loop
 * would just delay that state without adding value.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      staleTime: DEFAULT_STALE_TIME_MS,
    },
  },
});

// Native keeps the garment cache on disk (see `OfflineProvider`); web is unchanged.
if (offlineEnabled()) applyPersistedDefaults(queryClient);
