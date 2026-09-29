import createClient from 'openapi-fetch';

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
export const apiClient = createClient<paths>({
  baseUrl: API_BASE_URL,
  // openapi-fetch captures `globalThis.fetch` when the client is created.
  // Resolving it lazily per request keeps the client honoring later
  // replacements of the global (polyfills, and `jest.fn()` mocks in tests).
  fetch: (request) => globalThis.fetch(request),
});
