import {
  skipToken,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query';
import { useCallback, useEffect, useMemo } from 'react';

import { ApiError, unwrap } from '@/api-client/errors';
import { apiClient } from '@/api-client/http-client';
import { queryKeys } from '@/api-client/query-keys';
import {
  notIncludedIds,
  STEP_LABELS,
  tryOnDescription,
  tryOnStatus,
  type TryOnRender,
  type TryOnStatus,
} from '@/components/today/tryon-status';
import type { LookPiece } from '@/components/today/types';
import { prefetchTryOnImage } from '@/offline/images';

/** Default polling interval for `GET /tryon/{id}` while the render is not finished. */
export const TRYON_POLL_INTERVAL_MS = 1500;

/**
 * Consecutive failed polls of a render still in flight that are hidden behind the progress bar;
 * one more shows the error (about 7 s at the default interval). A successful poll resets the count.
 */
export const TRYON_MAX_POLL_FAILURES = 5;

/** A look -> render association older than this is dropped (see `pruneTryOn`). */
export const TRYON_MAX_AGE_MS = 14 * 24 * 60 * 60 * 1000;

/** What `byLook` stores: the latest render requested for a look. */
export type TryOnLink = { renderId: string };

/** Result of `POST /tryon`: the render and whether it came from the cache (200) or was queued (202). */
export type TryOnRequestResult = {
  render: TryOnRender;
  /** 200: the row already existed (done, or failed and not requeued); 202: queued or in flight. */
  httpStatus: 200 | 202;
  lookKey: string;
};

/** Shown between the tap and the first answer of `POST /tryon`. */
const WORKING_STATUS: TryOnStatus = { phase: 'working', progress: 0, label: STEP_LABELS.queued };

const isTerminal = (render: TryOnRender | undefined) =>
  render?.status === 'done' || render?.status === 'failed';

const isInFlight = (render: TryOnRender | undefined) =>
  render?.status === 'pending' || render?.status === 'claimed' || render?.status === 'running';

/** The identity of a look: its garment ids sorted (same rule as `proposalSet`), joined. */
export function lookKey(garmentIds: string[]): string {
  return [...garmentIds].sort().join(',');
}

/** A finished render is viewable offline once its image is on the disk cache. */
function keepImage(render: TryOnRender): void {
  if (render.status === 'done' && render.img) void prefetchTryOnImage(render.img);
}

/**
 * Polls that failed in a row, per render id. Module state rather than hook state so every
 * observer of the same `tryon.detail` key sees the count the query function updates (an observer
 * re-renders on each failed poll, because the query's error state changes). A good poll clears it.
 */
const pollFailures = new Map<string, number>();

/** Forgets the failed-poll count of a render (it was pruned from the cache). */
export const clearPollFailures = (id: string) => pollFailures.delete(id);

export async function fetchTryOn(id: string): Promise<TryOnRender> {
  return unwrap(await apiClient.GET('/tryon/{render_id}', { params: { path: { render_id: id } } }));
}

type UseTryOnOptions = {
  enabled?: boolean;
  /** Polling interval in ms while the render is pending, claimed or running. */
  refetchInterval?: number;
};

/**
 * `GET /tryon/{id}`, polled until the render is `done` or `failed`. A finished render never goes
 * stale (a retry arrives through `POST /tryon`, which seeds it again) and its image is prefetched to the disk cache.
 */
export function useTryOn(id: string | undefined, options: UseTryOnOptions = {}) {
  const { enabled = true, refetchInterval = TRYON_POLL_INTERVAL_MS } = options;
  const query = useQuery({
    queryKey: queryKeys.tryon.detail(id ?? ''),
    enabled: enabled && !!id,
    queryFn: async () => {
      const renderId = id as string;
      try {
        const render = await fetchTryOn(renderId);
        pollFailures.delete(renderId);
        keepImage(render);
        return render;
      } catch (error) {
        pollFailures.set(renderId, (pollFailures.get(renderId) ?? 0) + 1);
        throw error;
      }
    },
    staleTime: (query) => (isTerminal(query.state.data) ? Infinity : 0),
    refetchInterval: (query) => (isInFlight(query.state.data) ? refetchInterval : false),
  });
  return { ...query, failedPolls: (id && pollFailures.get(id)) || 0 };
}

/**
 * `POST /tryon` for a look's garment ids (shoes and accessories may be included: the API reports
 * them as unsupported). Stores the render id under the look's key and seeds the render's query
 * with the body, so a 200 `done` needs no further request. Failures surface as `ApiError`
 * (`TRYON_DISABLED`, `TRYON_NO_COMPATIBLE_GARMENTS`, `TRYON_GARMENT_NOT_READY`, ...).
 */
export function useRequestTryOn() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (garmentIds: string[]): Promise<TryOnRequestResult> => {
      const result = await apiClient.POST('/tryon', { body: { garment_ids: garmentIds } });
      const render = unwrap(result);
      return {
        render,
        httpStatus: result.response.status === 200 ? 200 : 202,
        lookKey: lookKey(garmentIds),
      };
    },
    onSuccess: ({ render, lookKey: key }) => {
      queryClient.setQueryData<TryOnLink>(queryKeys.tryon.byLook(key), { renderId: render.id });
      queryClient.setQueryData<TryOnRender>(queryKeys.tryon.detail(render.id), render);
      keepImage(render);
    },
  });
}

/**
 * Drops look -> render links older than `TRYON_MAX_AGE_MS` and the saved renders no link points
 * to (renders still being polled stay). Runs with Hoy's pruning of outfits, so the persisted
 * cache holds one render per recent look instead of growing for ever.
 */
export function pruneTryOn(queryClient: QueryClient, now: number = Date.now()): void {
  const cache = queryClient.getQueryCache();
  const kept = new Set<string>();
  for (const query of cache.findAll({ queryKey: queryKeys.tryon.byLooks() })) {
    // A link someone is looking at stays, however old: it would blank the canvas under the user.
    if (now - query.state.dataUpdatedAt > TRYON_MAX_AGE_MS && query.getObserversCount() === 0) {
      cache.remove(query);
    } else if (query.state.data) kept.add((query.state.data as TryOnLink).renderId);
  }
  for (const query of cache.findAll({ queryKey: queryKeys.tryon.details() })) {
    const id = String(query.queryKey[2]);
    if (!kept.has(id) && query.getObserversCount() === 0) {
      cache.remove(query);
      clearPollFailures(id);
    }
  }
}

/**
 * Everything the look canvas needs for one look: the stored render for its garment ids, its
 * polled state, `request()` to (re)start it and the view model from `tryOnStatus`.
 */
export function useLookTryOn(
  garmentIds: string[],
  pieces: LookPiece[],
  options: UseTryOnOptions = {},
) {
  const key = lookKey(garmentIds);
  const link = useQuery<TryOnLink>({
    queryKey: queryKeys.tryon.byLook(key),
    // Only ever written by `useRequestTryOn` or restored from disk: never fetched.
    queryFn: skipToken,
  });
  const renderId = link.data?.renderId;
  const query = useTryOn(renderId, options);
  const mutation = useRequestTryOn();
  const { mutate, reset } = mutation;
  const queryClient = useQueryClient();

  const request = useCallback(() => mutate(garmentIds), [mutate, garmentIds]);

  // The mutation outlives a change of look: only its own look's outcome counts.
  const own = mutation.variables !== undefined && lookKey(mutation.variables) === key;
  const lastRequest = own && mutation.data?.lookKey === key ? mutation.data : undefined;
  const requestError = own && mutation.isError ? mutation.error : undefined;
  const requesting = own && mutation.isPending;
  // A render the server no longer has (404) is not an error: the look simply has none.
  const gone = query.error instanceof ApiError && query.error.status === 404;
  const render = gone ? undefined : query.data;
  // The render was purged: forget the link so the look is untried again and can be requested anew.
  useEffect(() => {
    if (!gone || !renderId) return;
    queryClient.resetQueries({ queryKey: queryKeys.tryon.byLook(key), exact: true });
    queryClient.removeQueries({ queryKey: queryKeys.tryon.detail(renderId), exact: true });
    clearPollFailures(renderId);
  }, [gone, renderId, key, queryClient]);
  // A failed poll (network blip, 5xx) while the render is still in flight keeps the bar going: the
  // next poll may succeed. Only a failed request, a render that failed itself or a run of
  // `TRYON_MAX_POLL_FAILURES` failed polls shows the error.
  const pollError =
    gone || (isInFlight(render) && query.failedPolls < TRYON_MAX_POLL_FAILURES)
      ? undefined
      : (query.error ?? undefined);
  const error = requestError ?? pollError;
  // A fresh render beats the failure of an earlier request.
  const status = useMemo(
    () =>
      tryOnStatus(render, pieces, {
        error: requesting ? undefined : error,
        fromRequest: lastRequest?.httpStatus === 200 && lastRequest.render.id === render?.id,
      }),
    [render, pieces, error, requesting, lastRequest],
  );

  return {
    renderId,
    render,
    status: requesting && !render ? WORKING_STATUS : status,
    isRequesting: requesting,
    request,
    /** Clears the request error (e.g. when the user dismisses it). */
    dismissError: reset,
    notIncluded: notIncludedIds(render),
    description: tryOnDescription(render, pieces),
  };
}
