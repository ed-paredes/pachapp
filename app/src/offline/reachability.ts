import { skipToken, useQuery } from '@tanstack/react-query';
import { useSyncExternalStore } from 'react';

import { queryKeys } from '@/api-client/query-keys';

import { offlineEnabled } from './persistence';

/**
 * Whether the backend answers. This is not the device's connectivity (React Query's
 * `onlineManager`): the phone can have internet while the PC running the API is off.
 * - `unknown`: nothing requested yet.
 * - `offline`: the last request failed at network level (no answer, refused, timed out).
 * - `online`: the last request got an HTTP answer, whatever its status.
 */
export type BackendStatus = 'unknown' | 'online' | 'offline';

let status: BackendStatus = 'unknown';
const listeners = new Set<() => void>();

function setStatus(next: BackendStatus) {
  if (next === status) return;
  status = next;
  listeners.forEach((listener) => listener());
}

/** Any HTTP answer, even a 4xx/5xx, proves the backend is there. */
export function reportReachable() {
  setStatus('online');
}

/** A request failed before getting an answer. */
export function reportUnreachable() {
  setStatus('offline');
}

export function getBackendStatus(): BackendStatus {
  return status;
}

export function subscribeBackendStatus(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Back to `unknown`; tests only. */
export function resetBackendStatus() {
  setStatus('unknown');
}

export function useBackendStatus(): BackendStatus {
  return useSyncExternalStore(subscribeBackendStatus, getBackendStatus, getBackendStatus);
}

/** True when native cannot reach the backend. Always false on web, which just shows its errors. */
export function useIsOffline(): boolean {
  const current = useBackendStatus();
  return offlineEnabled() && current === 'offline';
}

/** When the saved data was last synced (ms), or `undefined` when nothing was ever saved. */
export function useLastSync(): number | undefined {
  // `skipToken`: read the (restored) cache entry, never fetch it.
  return useQuery({ queryKey: queryKeys.sync.last, queryFn: skipToken }).data as number | undefined;
}
