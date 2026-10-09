import AsyncStorage from '@react-native-async-storage/async-storage';
import { createAsyncStoragePersister } from '@tanstack/query-async-storage-persister';
import type { Query, QueryClient } from '@tanstack/react-query';
import type { PersistedClient, Persister } from '@tanstack/react-query-persist-client';
import Constants from 'expo-constants';
import { Platform } from 'react-native';

/** Persistence, sync and the offline UX exist on native only; web always reads the API. */
export function offlineEnabled(): boolean {
  return Platform.OS !== 'web';
}

/** How long a saved cache stays usable on disk. */
export const PERSIST_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;

/** Bump when the shape of a persisted query changes: it discards every saved cache. */
export const CACHE_SCHEMA_VERSION = 1;

export const PERSIST_STORAGE_KEY = 'pachapp-query-cache';

/** A saved cache is only restored by the app version and schema that wrote it. */
export function cacheBuster(): string {
  return `${Constants.expoConfig?.version ?? '0'}:${CACHE_SCHEMA_VERSION}`;
}

/**
 * Query families kept across restarts. Jobs and anything else stay in memory. `outfits` holds
 * Hoy's generated batches (a POST used as a query, never a mutation) so Hoy opens offline with
 * the last saved look. `tryon` holds the capabilities, the look -> render ids and the finished renders.
 */
const PERSISTED_ROOTS = ['garments', 'settings', 'sync', 'outfits', 'tryon'];

/**
 * Garment lists/details, settings, Hoy's looks and the sync stamp are written to disk once they hold data.
 * The check is on the data, not on `status === 'success'`: a refetch that fails offline turns the
 * status to `error` while the data stays, and dropping it then would wipe the saved copy.
 */
export function shouldPersistQuery(query: Pick<Query, 'queryKey' | 'state'>): boolean {
  if (query.state.data === undefined) return false;
  const root = String(query.queryKey[0] ?? '');
  if (!PERSISTED_ROOTS.includes(root)) return false;
  // A render being polled is noise: only a finished one is worth keeping (its image is on disk).
  if (root === 'tryon' && query.queryKey[1] === 'detail') {
    return (query.state.data as { status?: string }).status === 'done';
  }
  return true;
}

/**
 * A saved query is a copy of data that was good when it was saved, so it comes back as a finished
 * success. A refetch that failed offline leaves the in-memory query in `error` (with its data);
 * saved as it is, it would restore as `isError` and any screen that checks the error before the
 * data would show an error view instead of the wardrobe. The real state is rebuilt by the next
 * fetch. Applied on save and on restore, so caches written before this existed are fixed too.
 * Entries without data are dropped: as a success they would render as an empty wardrobe.
 */
export function settleQueries(persisted: PersistedClient): PersistedClient {
  return {
    ...persisted,
    clientState: {
      ...persisted.clientState,
      queries: persisted.clientState.queries
        .filter((entry) => entry.state.data !== undefined)
        .map((entry) => ({
          ...entry,
          state: {
            ...entry.state,
            status: 'success',
            fetchStatus: 'idle',
            error: null,
            errorUpdatedAt: 0,
            errorUpdateCount: 0,
            fetchFailureCount: 0,
            fetchFailureReason: null,
          },
        })),
    },
  };
}

/** Only garment lists, settings and the sync stamp: the lean copy used when a write is too big. */
function withoutDetails(persisted: PersistedClient): PersistedClient {
  return {
    ...persisted,
    clientState: {
      ...persisted.clientState,
      queries: persisted.clientState.queries.filter((entry) => entry.queryKey[1] !== 'detail'),
    },
  };
}

/**
 * AsyncStorage writes can fail (the Android row limit is ~2 MB; see `pruneSyncedCache` for the
 * expected size). The base persister swallows such failures silently, so they are logged here,
 * and one lean copy (no garment details: lists, settings and the sync stamp still fit) is tried
 * before giving up. The previous saved copy stays on disk when both fail. Never throws.
 */
export function createPersister(): Persister {
  const base = createAsyncStoragePersister({
    storage: AsyncStorage,
    key: PERSIST_STORAGE_KEY,
    retry: ({ persistedClient, error, errorCount }) => {
      console.warn(
        `Offline cache: could not save it (attempt ${errorCount}): ${
          error instanceof Error ? error.message : String(error)
        }`,
      );
      return Promise.resolve(errorCount === 1 ? withoutDetails(persistedClient) : undefined);
    },
  });
  return {
    persistClient: (persisted) => base.persistClient(settleQueries(persisted)),
    restoreClient: async () => {
      const restored = await base.restoreClient();
      return restored ? settleQueries(restored) : restored;
    },
    removeClient: () => base.removeClient(),
  };
}

/**
 * Persisted queries are never garbage collected in memory: a restored query without observers
 * would otherwise go after 5 minutes and be dropped from the saved copy too, so `gcTime` must be
 * at least `PERSIST_MAX_AGE_MS`. It is `Infinity` rather than 30 days because timers above ~24.8
 * days overflow and fire immediately. The saved copy itself expires through `maxAge`.
 */
export function applyPersistedDefaults(client: QueryClient): void {
  for (const root of PERSISTED_ROOTS) {
    client.setQueryDefaults([root], { gcTime: Infinity });
  }
}
