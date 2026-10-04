import {
  QueryClientProvider,
  useIsRestoring,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query';
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import { useEffect, useMemo, useRef, type ReactNode } from 'react';
import { AppState } from 'react-native';

import { apiClient } from '@/api-client/http-client';

import {
  cacheBuster,
  createPersister,
  offlineEnabled,
  PERSIST_MAX_AGE_MS,
  shouldPersistQuery,
} from './persistence';
import { getBackendStatus, subscribeBackendStatus } from './reachability';
import { syncWardrobe } from './sync';

/** How often to look for the backend while it is unreachable. */
export const RECONNECT_INTERVAL_MS = 15000;

/**
 * Re-syncs when the app comes back to the foreground after a failed run (the PC was off when it
 * opened). A successful sync is not repeated: it happens once per app start.
 */
function WardrobeSyncer() {
  const client = useQueryClient();
  const restoring = useIsRestoring();
  const lastRunFailed = useRef(false);

  useEffect(() => {
    if (restoring) return undefined;
    const run = () =>
      void syncWardrobe(client).then((result) => {
        lastRunFailed.current = !result.ok;
      });
    run();
    const subscription = AppState.addEventListener('change', (state) => {
      if (state === 'active' && lastRunFailed.current) run();
    });
    return () => subscription.remove();
  }, [client, restoring]);

  return null;
}

/**
 * While the backend is unreachable, asks it for `/health` every 15 s and when the app returns to
 * the foreground. The first answer flips the status back to online (the request itself reports
 * it, see `trackedFetch`); then the screens refresh and the wardrobe syncs again, no restart.
 */
function ReconnectWatcher() {
  const client = useQueryClient();

  useEffect(() => {
    let offlineBefore = getBackendStatus() === 'offline';
    let timer: ReturnType<typeof setInterval> | undefined;
    const ping = () => void apiClient.GET('/health').catch(() => undefined);
    const stop = () => {
      clearInterval(timer);
      timer = undefined;
    };
    const apply = () => {
      const offline = getBackendStatus() === 'offline';
      if (offline && !timer) timer = setInterval(ping, RECONNECT_INTERVAL_MS);
      if (!offline) stop();
      if (offlineBefore && !offline) {
        void client.refetchQueries({ type: 'active' });
        void syncWardrobe(client);
      }
      offlineBefore = offline;
    };
    apply();
    const unsubscribe = subscribeBackendStatus(apply);
    const appState = AppState.addEventListener('change', (state) => {
      if (state === 'active' && getBackendStatus() === 'offline') ping();
    });
    return () => {
      unsubscribe();
      appState.remove();
      stop();
    };
  }, [client]);

  return null;
}

/**
 * Web: a plain `QueryClientProvider`, nothing saved, nothing synced. Native: the cache is saved
 * to AsyncStorage (`PersistQueryClientProvider`), restored at start, and the wardrobe is synced
 * once the saved copy is back.
 */
export function OfflineProvider({
  client,
  children,
}: {
  client: QueryClient;
  children: ReactNode;
}) {
  const persistOptions = useMemo(
    () =>
      offlineEnabled()
        ? {
            persister: createPersister(),
            maxAge: PERSIST_MAX_AGE_MS,
            buster: cacheBuster(),
            dehydrateOptions: { shouldDehydrateQuery: shouldPersistQuery },
          }
        : null,
    [],
  );

  if (!persistOptions) return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return (
    <PersistQueryClientProvider client={client} persistOptions={persistOptions}>
      <WardrobeSyncer />
      <ReconnectWatcher />
      {children}
    </PersistQueryClientProvider>
  );
}
