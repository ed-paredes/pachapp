import { QueryClient } from '@tanstack/react-query';

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
    },
  },
});
