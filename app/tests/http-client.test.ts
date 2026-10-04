import { ApiError, isNetworkError, RequestTimeoutError } from '../src/api-client/errors';
import { apiClient, READ_TIMEOUT_MS } from '../src/api-client/http-client';
import { getBackendStatus, reportReachable, resetBackendStatus } from '../src/offline/reachability';
import { Platform } from 'react-native';

const realOS = Platform.OS;
const realFetch = globalThis.fetch;
const setPlatform = (os: string) =>
  Object.defineProperty(Platform, 'OS', { configurable: true, get: () => os });

/** A fetch that never answers and rejects the way `fetch` does when its signal aborts. */
function hangingFetch() {
  return jest.fn(
    (request: Request) =>
      new Promise((_resolve, reject) => {
        const abort = () => reject(new DOMException('The operation was aborted.', 'AbortError'));
        if (request.signal.aborted) abort();
        else request.signal.addEventListener('abort', abort);
      }),
  );
}

beforeEach(() => {
  reportReachable();
});

afterEach(() => {
  jest.useRealTimers();
  globalThis.fetch = realFetch;
  setPlatform(realOS);
  resetBackendStatus();
});

describe('caller cancellation (native read)', () => {
  beforeEach(() => setPlatform('android'));

  it('aborts the request when the caller aborts, and the backend stays reachable', async () => {
    // Fake timers: only the caller's abort can end this request, never the 15 s timeout.
    jest.useFakeTimers();
    const fetchMock = hangingFetch();
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    const caller = new AbortController();

    const pending = apiClient.GET('/health', { signal: caller.signal }).catch((error) => error);
    await Promise.resolve();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const sent = fetchMock.mock.calls[0][0];
    expect(sent.signal.aborted).toBe(false);

    caller.abort();
    const error = await pending;

    expect(sent.signal.aborted).toBe(true);
    expect(error).toBeDefined();
    expect(jest.getTimerCount()).toBe(0);
    expect(isNetworkError(error)).toBe(false);
    expect(getBackendStatus()).toBe('online');
  });

  it('a signal that was already aborted never reaches the network as a live request', async () => {
    const fetchMock = hangingFetch();
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    const caller = new AbortController();
    caller.abort();

    await apiClient.GET('/health', { signal: caller.signal }).catch(() => undefined);

    expect(getBackendStatus()).toBe('online');
    for (const [sent] of fetchMock.mock.calls) expect(sent.signal.aborted).toBe(true);
  });

  it('our own timeout still marks the backend offline and rejects with a timeout error', async () => {
    jest.useFakeTimers();
    globalThis.fetch = hangingFetch() as unknown as typeof fetch;

    const pending = apiClient.GET('/health').catch((error) => error);
    await jest.advanceTimersByTimeAsync(READ_TIMEOUT_MS);
    const error = await pending;

    expect(error).toBeInstanceOf(RequestTimeoutError);
    expect(isNetworkError(error)).toBe(true);
    expect(getBackendStatus()).toBe('offline');
  });

  it('removes its listener from the caller signal and clears the timer', async () => {
    jest.useFakeTimers();
    globalThis.fetch = jest.fn(async () => new Response('{}', { status: 200 })) as never;
    const caller = new AbortController();
    const add = jest.spyOn(AbortSignal.prototype, 'addEventListener');
    const remove = jest.spyOn(AbortSignal.prototype, 'removeEventListener');

    await apiClient.GET('/health', { signal: caller.signal });

    // `Request` and openapi-fetch add listeners of their own; ours is the one named below.
    const ours = add.mock.calls.find(
      ([, listener]) => (listener as { name?: string }).name === 'onCallerAbort',
    );
    expect(ours).toBeDefined();
    expect(remove.mock.calls.some(([, listener]) => listener === ours?.[1])).toBe(true);
    expect(jest.getTimerCount()).toBe(0);
  });

  it('a late abort after the response does nothing', async () => {
    globalThis.fetch = jest.fn(async () => new Response('{}', { status: 200 })) as never;
    const caller = new AbortController();
    await apiClient.GET('/health', { signal: caller.signal });
    caller.abort();
    expect(getBackendStatus()).toBe('online');
  });
});

describe.each(['android', 'web'])('a caller abort on %s', (os) => {
  it.each(['GET', 'POST'])('is not reported as unreachable (%s)', async (method) => {
    setPlatform(os);
    globalThis.fetch = hangingFetch() as unknown as typeof fetch;
    const caller = new AbortController();

    const pending =
      method === 'GET'
        ? apiClient.GET('/health', { signal: caller.signal })
        : apiClient.POST('/settings' as never, { signal: caller.signal } as never);
    pending.catch(() => undefined);
    await Promise.resolve();
    caller.abort();
    await pending.catch(() => undefined);

    expect(getBackendStatus()).toBe('online');
  });
});

describe('a genuine network failure', () => {
  it.each(['android', 'web'])('marks the backend offline on %s', async (os) => {
    setPlatform(os);
    globalThis.fetch = jest.fn(() =>
      Promise.reject(new TypeError('Network request failed')),
    ) as never;
    await apiClient.GET('/health').catch(() => undefined);
    expect(getBackendStatus()).toBe('offline');
  });

  it('a body that does not parse is not a connection problem', async () => {
    setPlatform('android');
    globalThis.fetch = jest.fn(async () => new Response('<html>', { status: 200 })) as never;
    await apiClient.GET('/health').catch(() => undefined);
    expect(getBackendStatus()).toBe('online');
  });
});

describe('isNetworkError', () => {
  it('is true for fetch failures and our timeout', () => {
    expect(isNetworkError(new TypeError('Network request failed'))).toBe(true);
    expect(isNetworkError(new RequestTimeoutError())).toBe(true);
  });

  it('is false for HTTP answers, caller aborts, parse errors and plain bugs', () => {
    expect(isNetworkError(new ApiError('boom', 500))).toBe(false);
    expect(isNetworkError(new DOMException('aborted', 'AbortError'))).toBe(false);
    expect(isNetworkError(new SyntaxError('Unexpected token <'))).toBe(false);
    expect(isNetworkError(new RangeError('x'))).toBe(false);
    expect(isNetworkError(new Error('x'))).toBe(false);
    expect(isNetworkError('nope')).toBe(false);
    expect(isNetworkError(undefined)).toBe(false);
  });
});
