import AsyncStorage from '@react-native-async-storage/async-storage';
import { createAsyncStoragePersister } from '@tanstack/query-async-storage-persister';
import type { Query, QueryClient } from '@tanstack/react-query';
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

/** Query families kept across restarts. Jobs and anything else stay in memory. */
const PERSISTED_ROOTS = ['garments', 'settings', 'sync'];

/**
 * Garment lists/details, settings and the sync stamp are written to disk once they hold data.
 * The check is on the data, not on `status === 'success'`: a refetch that fails offline turns the
 * status to `error` while the data stays, and dropping it then would wipe the saved copy.
 */
export function shouldPersistQuery(query: Pick<Query, 'queryKey' | 'state'>): boolean {
  return (
    query.state.data !== undefined && PERSISTED_ROOTS.includes(String(query.queryKey[0] ?? ''))
  );
}

export function createPersister() {
  return createAsyncStoragePersister({ storage: AsyncStorage, key: PERSIST_STORAGE_KEY });
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
