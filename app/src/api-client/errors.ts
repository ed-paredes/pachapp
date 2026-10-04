/**
 * Error thrown by every API hook when the server answers with a non-2xx
 * status. Carries the HTTP status and, when the body is the API error
 * envelope (`{"error": {"code", "message"}}`, API-REQ-001), its code and
 * message so screens can show the server's own (Spanish) text.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(message: string, status: number, code: string | null = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

type Envelope = { error?: { code?: unknown; message?: unknown } };

function readEnvelope(body: unknown): { code: string | null; message: string | null } {
  const inner = (body as Envelope | null | undefined)?.error;
  if (inner && typeof inner === 'object') {
    return {
      code: typeof inner.code === 'string' ? inner.code : null,
      message: typeof inner.message === 'string' && inner.message ? inner.message : null,
    };
  }
  return { code: null, message: null };
}

/**
 * Turns an `openapi-fetch` result into its data or throws an `ApiError`.
 * Same contract as `useHealth` (`!response.ok || error` throws), plus the
 * envelope's message when the body carries one.
 */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  const { data, error, response } = result;
  if (!response.ok || error !== undefined) {
    const { code, message } = readEnvelope(error);
    throw new ApiError(
      message ?? `Request failed with status ${response.status}`,
      response.status,
      code,
    );
  }
  return data as T;
}

/**
 * True when a request failed before the server answered (no connection, refused, timed out):
 * `fetch` rejects with a `TypeError` or an abort error. Any HTTP answer, even a 5xx, is an
 * `ApiError` and means the backend is reachable.
 */
export function isNetworkError(error: unknown): boolean {
  return !(error instanceof ApiError);
}
