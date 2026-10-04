/**
 * Error thrown by every API hook when the server answers with a non-2xx
 * status. Carries the HTTP status and, when the body is the API error
 * envelope (`{"error": {"code", "message"}}`, API-REQ-001), its code and
 * message so screens can show the server's own (Spanish) text.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  /** The envelope's `details` (e.g. the `date` of a `WEAR_LOG_CONFLICT`), when it has any. */
  readonly details: Record<string, unknown> | null;

  constructor(
    message: string,
    status: number,
    code: string | null = null,
    details: Record<string, unknown> | null = null,
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

type Envelope = { error?: { code?: unknown; message?: unknown; details?: unknown } };

function readEnvelope(body: unknown): {
  code: string | null;
  message: string | null;
  details: Record<string, unknown> | null;
} {
  const inner = (body as Envelope | null | undefined)?.error;
  if (inner && typeof inner === 'object') {
    const details = inner.details;
    return {
      code: typeof inner.code === 'string' ? inner.code : null,
      message: typeof inner.message === 'string' && inner.message ? inner.message : null,
      details:
        details && typeof details === 'object' && !Array.isArray(details)
          ? (details as Record<string, unknown>)
          : null,
    };
  }
  return { code: null, message: null, details: null };
}

/**
 * Turns an `openapi-fetch` result into its data or throws an `ApiError`.
 * Same contract as `useHealth` (`!response.ok || error` throws), plus the
 * envelope's message when the body carries one.
 */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  const { data, error, response } = result;
  if (!response.ok || error !== undefined) {
    const { code, message, details } = readEnvelope(error);
    throw new ApiError(
      message ?? `Request failed with status ${response.status}`,
      response.status,
      code,
      details,
    );
  }
  return data as T;
}

/** Thrown by the HTTP layer when a native read got no answer within `READ_TIMEOUT_MS`. */
export class RequestTimeoutError extends Error {
  constructor() {
    super('The request timed out');
    this.name = 'RequestTimeoutError';
  }
}

/**
 * True when a request failed before the server answered: `fetch` rejects with a `TypeError`
 * (no connection, refused, DNS) or our own `RequestTimeoutError`. Everything else is not a
 * network failure: an HTTP answer, even a 5xx, is an `ApiError` (the backend is reachable), a
 * caller abort (`AbortError`) was the app's own decision, and a `SyntaxError` from a body that
 * does not parse or any other programming error is a bug to surface, not a lost connection.
 */
export function isNetworkError(error: unknown): boolean {
  return error instanceof TypeError || error instanceof RequestTimeoutError;
}
