import {
  QueryClientProvider,
  useIsRestoring,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query';
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import { useEffect, useMemo, useRef, type ReactNode } from 'react';
import { AppState } from 'react-native';

import {
  cacheBuster,
  createPersister,
  offlineEnabled,
  PERSIST_MAX_AGE_MS,
  shouldPersistQuery,
} from './persistence';
import { syncWardrobe } from './sync';

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
      {children}
    </PersistQueryClientProvider>
  );
}
