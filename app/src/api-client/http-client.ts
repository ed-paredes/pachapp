import createClient from 'openapi-fetch';

import { offlineEnabled } from '@/offline/persistence';
import { reportReachable, reportUnreachable } from '@/offline/reachability';

import { API_BASE_URL } from './config';
import { isNetworkError, RequestTimeoutError } from './errors';
import type { paths } from './schema';

/**
 * Typed fetch client built on the generated OpenAPI `paths` (`schema.ts`).
 *
 * Uses `openapi-fetch` — a small (~2KB), dependency-free wrapper that turns
 * the generated types into a typed `GET`/`POST`/... client without any code
 * generation of its own — rather than hand-writing per-endpoint fetch
 * wrappers, so new endpoints only need their OpenAPI types regenerated.
 */
/** A GET that gets no answer in this long counts as unreachable (native only). */
export const READ_TIMEOUT_MS = 15000;

/**
 * Gives a read its own timeout without losing the caller's cancellation (React Query aborts the
 * request through `request.signal`). `AbortSignal.any` is not assumed to exist on Hermes, so the
 * two signals are joined by hand and the listener is removed in `dispose`.
 */
function withReadTimeout(request: Request) {
  const controller = new AbortController();
  const caller = request.signal;
  let timedOut = false;
  const onCallerAbort = () => controller.abort();
  if (caller.aborted) controller.abort();
  else caller.addEventListener('abort', onCallerAbort);
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, READ_TIMEOUT_MS);
  return {
    request: new Request(request, { signal: controller.signal }),
    timedOut: () => timedOut,
    dispose: () => {
      clearTimeout(timer);
      caller.removeEventListener('abort', onCallerAbort);
    },
  };
}

/**
 * Sends the request and records whether the backend answered: any HTTP response (even a 5xx)
 * means reachable, a network failure or a timed out read means it is not. A request the caller
 * aborted says nothing about the backend and changes nothing. Uploads and other writes get no
 * timeout, since a large photo over Wi-Fi can legitimately take long.
 */
async function trackedFetch(request: Request): Promise<Response> {
  const guarded = offlineEnabled() && request.method === 'GET' ? withReadTimeout(request) : null;
  try {
    const response = await globalThis.fetch(guarded?.request ?? request);
    reportReachable();
    return response;
  } catch (error) {
    if (guarded?.timedOut() && !request.signal.aborted) {
      reportUnreachable();
      throw new RequestTimeoutError();
    }
    if (!request.signal.aborted && isNetworkError(error)) reportUnreachable();
    throw error;
  } finally {
    guarded?.dispose();
  }
}

export const apiClient = createClient<paths>({
  baseUrl: API_BASE_URL,
  // openapi-fetch captures `globalThis.fetch` when the client is created.
  // Resolving it lazily per request keeps the client honoring later
  // replacements of the global (polyfills, and `jest.fn()` mocks in tests).
  fetch: trackedFetch,
});
