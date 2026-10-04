import createClient from 'openapi-fetch';

import { offlineEnabled } from '@/offline/persistence';
import { reportReachable, reportUnreachable } from '@/offline/reachability';

import { API_BASE_URL } from './config';
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
 * Sends the request and records whether the backend answered: any HTTP response (even a 5xx)
 * means reachable, a rejected `fetch` or a timed out read means it is not. Uploads and other
 * writes get no timeout, since a large photo over Wi-Fi can legitimately take long.
 */
async function trackedFetch(request: Request): Promise<Response> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let outgoing = request;
  if (offlineEnabled() && request.method === 'GET') {
    const controller = new AbortController();
    timer = setTimeout(() => controller.abort(), READ_TIMEOUT_MS);
    outgoing = new Request(request, { signal: controller.signal });
  }
  try {
    const response = await globalThis.fetch(outgoing);
    reportReachable();
    return response;
  } catch (error) {
    reportUnreachable();
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

export const apiClient = createClient<paths>({
  baseUrl: API_BASE_URL,
  // openapi-fetch captures `globalThis.fetch` when the client is created.
  // Resolving it lazily per request keeps the client honoring later
  // replacements of the global (polyfills, and `jest.fn()` mocks in tests).
  fetch: trackedFetch,
});
