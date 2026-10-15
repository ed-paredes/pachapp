import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react-native';
import { Image } from 'expo-image';
import type { ReactNode } from 'react';
import { Platform } from 'react-native';

import { ApiError } from '../src/api-client/errors';
import { queryKeys } from '../src/api-client/query-keys';
import type { LookPiece } from '../src/components/today/types';
import {
  lookKey,
  pruneTryOn,
  TRYON_MAX_AGE_MS,
  resetPollFailures,
  TRYON_MAX_POLL_FAILURES,
  useLookTryOn,
  useRequestTryOn,
  useTryOn,
} from '../src/hooks/useTryOn';
import { usePatchSettings } from '../src/hooks/useSettings';
import { isLookTryable, useTryOnCapabilities } from '../src/hooks/useTryOnCapabilities';
import { shouldPersistQuery } from '../src/offline/persistence';

const clients: QueryClient[] = [];

function makeClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { gcTime: 0 } },
  });
  clients.push(client);
  return client;
}

function wrapperFor(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const fetchMock = () => globalThis.fetch as jest.Mock;
const requestAt = (n: number) => fetchMock().mock.calls[n][0] as Request;

const render = (patch: Record<string, unknown> = {}) => ({
  id: 'r1',
  status: 'pending',
  step: null,
  progress: 0,
  error: null,
  img: null,
  garment_ids: ['g1', 'g2'],
  skipped_garment_ids: [],
  unsupported_garment_ids: [],
  created_at: '2026-10-09T10:00:00Z',
  ...patch,
});
const apiError = (code: string, status = 422) =>
  json({ error: { code, message: code, details: null } }, status);

const PIECES: LookPiece[] = [
  { garmentId: 'g1', role: 'bottom', name: 'pantalón beige', imageUri: null },
  { garmentId: 'g2', role: 'top', name: 'jersey negro', imageUri: null },
  { garmentId: 'g3', role: 'shoes', name: 'botas', imageUri: null },
];

const realOS = Platform.OS;
const setPlatform = (os: string) =>
  Object.defineProperty(Platform, 'OS', { configurable: true, get: () => os });
let prefetch: jest.SpyInstance;

describe('try-on data layer', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    resetPollFailures();
    globalThis.fetch = jest.fn();
    setPlatform('android');
    prefetch = jest.spyOn(Image, 'prefetch').mockResolvedValue(true);
    jest.spyOn(Image, 'getCachePathAsync').mockResolvedValue(null);
  });

  afterEach(async () => {
    await cleanup();
    clients.splice(0).forEach((client) => client.clear());
    globalThis.fetch = originalFetch;
    setPlatform(realOS);
    jest.restoreAllMocks();
  });

  it('lookKey sorts the ids, so the order of a look does not matter', () => {
    expect(lookKey(['b', 'a', 'c'])).toBe('a,b,c');
    expect(lookKey(['c', 'a', 'b'])).toBe(lookKey(['a', 'b', 'c']));
  });

  it('useTryOnCapabilities reads the endpoint and isLookTryable needs a supported piece', async () => {
    const caps = {
      enabled: true,
      supported_categories: ['top', 'bottom'],
      max_passes: 3,
      genders: ['woman', 'man'],
      skin_tones: [{ id: 1, hex: '#F3DBC8' }],
    };
    fetchMock().mockResolvedValueOnce(json(caps));
    const { result } = await renderHook(() => useTryOnCapabilities(), {
      wrapper: wrapperFor(makeClient()),
    });
    await waitFor(() => expect(result.current.data).toEqual(caps));
    expect(requestAt(0).url).toContain('/tryon/capabilities');

    expect(isLookTryable([{ role: 'shoes' }, { role: 'top' }], caps)).toBe(true);
    expect(isLookTryable([{ role: 'shoes' }, { role: 'accessory' }], caps)).toBe(false);
    expect(isLookTryable([{ role: 'top' }], { ...caps, enabled: false })).toBe(false);
    expect(isLookTryable([{ role: 'top' }], undefined)).toBe(false);
  });

  it('useRequestTryOn: 202 stores the link and seeds the render, then useTryOn polls to done', async () => {
    const client = makeClient();
    fetchMock()
      .mockResolvedValueOnce(json(render(), 202))
      .mockResolvedValueOnce(json(render({ status: 'running', step: 'dressing_1', progress: 30 })))
      .mockResolvedValueOnce(json(render({ status: 'done', progress: 100, img: 'tryon/r1.webp' })));

    const request = await renderHook(() => useRequestTryOn(), { wrapper: wrapperFor(client) });
    let outcome: Awaited<ReturnType<typeof request.result.current.mutateAsync>> | undefined;
    await act(async () => {
      outcome = await request.result.current.mutateAsync(['g2', 'g1']);
    });
    expect(outcome?.httpStatus).toBe(202);
    expect(await requestAt(0).clone().json()).toEqual({ garment_ids: ['g2', 'g1'] });
    expect(client.getQueryData(queryKeys.tryon.byLook('g1,g2'))).toEqual({ renderId: 'r1' });
    expect(client.getQueryData(queryKeys.tryon.detail('r1'))).toMatchObject({ status: 'pending' });

    const poll = await renderHook(() => useTryOn('r1', { refetchInterval: 10 }), {
      wrapper: wrapperFor(client),
    });
    await waitFor(() => expect(poll.result.current.data?.status).toBe('done'));
    expect(fetchMock()).toHaveBeenCalledTimes(3);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 60));
    });
    expect(fetchMock()).toHaveBeenCalledTimes(3);
    await waitFor(() =>
      expect(prefetch).toHaveBeenCalledWith(['http://localhost:8000/images/tryon/r1.webp'], 'disk'),
    );
  });

  it('a 200 done is seeded, prefetched and never polled', async () => {
    const client = makeClient();
    fetchMock().mockResolvedValueOnce(
      json(render({ status: 'done', progress: 100, img: 'tryon/r1.webp' }), 200),
    );
    const { result } = await renderHook(
      () => useLookTryOn(['g1', 'g2'], PIECES, { refetchInterval: 10 }),
      { wrapper: wrapperFor(client) },
    );
    expect(result.current.status.phase).toBe('idle');
    await act(async () => result.current.request());
    await waitFor(() => expect(result.current.status.phase).toBe('done'));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 60));
    });
    expect(fetchMock()).toHaveBeenCalledTimes(1);
    expect(prefetch).toHaveBeenCalledTimes(1);
    expect(result.current.description).toBe(
      'Outfit puesto en un modelo: jersey negro, pantalón beige',
    );
  });

  it('a 200 failed with a transient error is "later"; a polled one is "retry"', async () => {
    const client = makeClient();
    fetchMock().mockResolvedValueOnce(
      json(render({ status: 'failed', error: 'engine_error', progress: 20 }), 200),
    );
    const { result } = await renderHook(() => useLookTryOn(['g1', 'g2'], PIECES), {
      wrapper: wrapperFor(client),
    });
    await act(async () => result.current.request());
    await waitFor(() => expect(result.current.status.errorKind).toBe('later'));

    // The same failure seen by polling (202 request) is retryable at once.
    const other = makeClient();
    fetchMock()
      .mockResolvedValueOnce(json(render({ id: 'r2' }), 202))
      .mockResolvedValueOnce(json(render({ id: 'r2', status: 'failed', error: 'engine_error' })));
    const second = await renderHook(
      () => useLookTryOn(['g1', 'g3'], PIECES, { refetchInterval: 10 }),
      { wrapper: wrapperFor(other) },
    );
    await act(async () => second.result.current.request());
    await waitFor(() => expect(second.result.current.status.errorKind).toBe('retry'));
  });

  it('surfaces ApiError codes of the request and keeps no link', async () => {
    const client = makeClient();
    fetchMock().mockResolvedValueOnce(apiError('TRYON_GARMENT_NOT_READY'));
    const { result } = await renderHook(() => useLookTryOn(['g1', 'g2'], PIECES), {
      wrapper: wrapperFor(client),
    });
    await act(async () => result.current.request());
    await waitFor(() => expect(result.current.status.phase).toBe('error'));
    expect(result.current.status.errorKind).toBe('later');
    expect(client.getQueryData(queryKeys.tryon.byLook('g1,g2'))).toBeUndefined();

    const raw = await renderHook(() => useRequestTryOn(), { wrapper: wrapperFor(makeClient()) });
    fetchMock().mockResolvedValueOnce(apiError('TRYON_DISABLED', 503));
    await act(async () => {
      await expect(raw.result.current.mutateAsync(['g1'])).rejects.toMatchObject({
        constructor: ApiError,
        code: 'TRYON_DISABLED',
      });
    });
  });

  it('a network failure on the request reads as retry', async () => {
    fetchMock().mockRejectedValueOnce(new TypeError('Network request failed'));
    const { result } = await renderHook(() => useLookTryOn(['g1'], PIECES), {
      wrapper: wrapperFor(makeClient()),
    });
    await act(async () => result.current.request());
    await waitFor(() => expect(result.current.status.errorKind).toBe('retry'));
  });

  it('keeps the look -> render association across re-renders and look switches', async () => {
    const client = makeClient();
    client.setQueryData(queryKeys.tryon.byLook('g1,g2'), { renderId: 'r1' });
    client.setQueryData(
      queryKeys.tryon.detail('r1'),
      render({ status: 'done', img: 'tryon/r1.webp' }),
    );
    const { result, rerender } = await renderHook(
      ({ ids }: { ids: string[] }) => useLookTryOn(ids, PIECES),
      { wrapper: wrapperFor(client), initialProps: { ids: ['g2', 'g1'] } },
    );
    expect(result.current.renderId).toBe('r1');
    expect(result.current.status.phase).toBe('done');

    await rerender({ ids: ['g1', 'g3'] });
    expect(result.current.renderId).toBeUndefined();
    expect(result.current.status.phase).toBe('idle');

    await rerender({ ids: ['g1', 'g2'] });
    expect(result.current.renderId).toBe('r1');
    expect(result.current.status.phase).toBe('done');
    expect(fetchMock()).not.toHaveBeenCalled();
  });

  it('treats a 404 render as no render, so the look can be requested again', async () => {
    const client = makeClient();
    client.setQueryData(queryKeys.tryon.byLook('g1,g2'), { renderId: 'gone' });
    fetchMock().mockResolvedValueOnce(apiError('NOT_FOUND', 404));
    const { result } = await renderHook(() => useLookTryOn(['g1', 'g2'], PIECES), {
      wrapper: wrapperFor(client),
    });
    await waitFor(() => expect(fetchMock()).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(result.current.render).toBeUndefined());
    expect(result.current.status.phase).toBe('idle');
  });

  it('forgets the look -> render link after a 404, so "Verlo puesto" can request it again (R3-003)', async () => {
    const client = makeClient();
    client.setQueryData(queryKeys.tryon.byLook('g1,g2'), { renderId: 'gone' });
    fetchMock()
      .mockResolvedValueOnce(apiError('NOT_FOUND', 404))
      .mockResolvedValueOnce(json(render({ id: 'r2' }), 202));
    const { result } = await renderHook(() => useLookTryOn(['g1', 'g2'], PIECES), {
      wrapper: wrapperFor(client),
    });
    await waitFor(() => expect(result.current.renderId).toBeUndefined());
    expect(client.getQueryData(queryKeys.tryon.byLook('g1,g2'))).toBeUndefined();
    expect(client.getQueryData(queryKeys.tryon.detail('gone'))).toBeUndefined();
    expect(result.current.status.phase).toBe('idle');
    // Back to untried: a new request links the new render.
    await act(async () => result.current.request());
    await waitFor(() => expect(result.current.renderId).toBe('r2'));
    expect(requestAt(1).method).toBe('POST');
  });
});

describe('try-on follows the model settings', () => {
  const originalFetch = globalThis.fetch;
  const SETTINGS = { tryon_gender: 'woman', tryon_skin_tone: 3 };

  beforeEach(() => {
    resetPollFailures();
    globalThis.fetch = jest.fn();
    jest.spyOn(Image, 'prefetch').mockResolvedValue(true);
    jest.spyOn(Image, 'getCachePathAsync').mockResolvedValue(null);
  });

  afterEach(async () => {
    await cleanup();
    clients.splice(0).forEach((client) => client.clear());
    globalThis.fetch = originalFetch;
    jest.restoreAllMocks();
  });

  function seeded() {
    const client = makeClient();
    client.setQueryData(queryKeys.settings, SETTINGS);
    client.setQueryData(queryKeys.tryon.byLook('g1,g2'), { renderId: 'r1' });
    client.setQueryData(
      queryKeys.tryon.detail('r1'),
      render({ status: 'done', img: 'tryon/r1_t3.webp' }),
    );
    return client;
  }

  it('a new tone refetches the render, so Hoy gets the new variant', async () => {
    const client = seeded();
    fetchMock().mockImplementation(async (request: Request) =>
      request.method === 'PATCH'
        ? json({ ...SETTINGS, tryon_skin_tone: 5 })
        : json(render({ status: 'done', img: 'tryon/r1_t5.webp' })),
    );
    const { result } = await renderHook(
      () => ({ look: useLookTryOn(['g1', 'g2'], PIECES), patch: usePatchSettings() }),
      { wrapper: wrapperFor(client) },
    );
    expect(result.current.look.render?.img).toBe('tryon/r1_t3.webp');

    await act(() => result.current.patch.mutateAsync({ tryon_skin_tone: 5 }));

    await waitFor(() => expect(result.current.look.render?.img).toBe('tryon/r1_t5.webp'));
    expect(requestAt(1).url).toContain('/tryon/r1');
    // The link survives: same render, other image.
    expect(result.current.look.renderId).toBe('r1');
  });

  it('a new gender forgets the links, so the look is untried and can be requested again', async () => {
    const client = seeded();
    fetchMock().mockResolvedValue(json({ ...SETTINGS, tryon_gender: 'man' }));
    const { result } = await renderHook(
      () => ({ look: useLookTryOn(['g1', 'g2'], PIECES), patch: usePatchSettings() }),
      { wrapper: wrapperFor(client) },
    );
    expect(result.current.look.status.phase).toBe('done');

    await act(() => result.current.patch.mutateAsync({ tryon_gender: 'man' }));

    await waitFor(() => expect(result.current.look.status.phase).toBe('idle'));
    expect(result.current.look.renderId).toBeUndefined();
    expect(client.getQueryData(queryKeys.tryon.byLooks())).toBeUndefined();
  });

  it('saving unrelated settings leaves the render alone', async () => {
    const client = seeded();
    fetchMock().mockResolvedValue(json({ ...SETTINGS, no_repeat_days: 9 }));
    const { result } = await renderHook(
      () => ({ look: useLookTryOn(['g1', 'g2'], PIECES), patch: usePatchSettings() }),
      { wrapper: wrapperFor(client) },
    );

    await act(() => result.current.patch.mutateAsync({ no_repeat_days: 9 }));

    expect(result.current.look.status.phase).toBe('done');
    // Only the PATCH went out; the finished render was not read again.
    expect(fetchMock()).toHaveBeenCalledTimes(1);
  });
});

describe('try-on regressions', () => {
  const originalFetch = globalThis.fetch;
  // The failed-poll counts are module state: do not carry them from one case to the next.
  beforeEach(() => {
    resetPollFailures();
    globalThis.fetch = jest.fn();
    setPlatform('android');
    jest.spyOn(Image, 'prefetch').mockResolvedValue(true);
    jest.spyOn(Image, 'getCachePathAsync').mockResolvedValue(null);
  });
  afterEach(async () => {
    await cleanup();
    // A poll still in flight would settle after the reset and count for the next case.
    await Promise.all(clients.map((client) => waitFor(() => expect(client.isFetching()).toBe(0))));
    clients.splice(0).forEach((client) => client.clear());
    resetPollFailures();
    globalThis.fetch = originalFetch;
    setPlatform(realOS);
    jest.restoreAllMocks();
  });

  it('a failed poll while the render is in flight keeps the working state (R3-002)', async () => {
    const client = makeClient();
    client.setQueryData(queryKeys.tryon.byLook('g1,g2'), { renderId: 'r1' });
    client.setQueryData(
      queryKeys.tryon.detail('r1'),
      render({ status: 'running', step: 'dressing_1', progress: 30 }),
    );
    fetchMock()
      .mockRejectedValueOnce(new TypeError('Network request failed'))
      .mockResolvedValueOnce(json(render({ status: 'done', progress: 100, img: 'tryon/r1.webp' })));
    const { result } = await renderHook(
      () => useLookTryOn(['g1', 'g2'], PIECES, { refetchInterval: 10 }),
      { wrapper: wrapperFor(client) },
    );
    await waitFor(() => expect(fetchMock()).toHaveBeenCalledTimes(1));
    expect(result.current.status.phase).toBe('working');
    await waitFor(() => expect(result.current.status.phase).toBe('done'));
  });

  it('shows the error after too many failed polls in a row; a good poll resets the count', async () => {
    const client = makeClient();
    client.setQueryData(queryKeys.tryon.byLook('g1,g2'), { renderId: 'r1' });
    client.setQueryData(queryKeys.tryon.detail('r1'), render({ status: 'running', progress: 30 }));
    // The mount refetch of the seeded (stale) render.
    fetchMock().mockResolvedValueOnce(json(render({ status: 'running' })));
    const { result } = await renderHook(
      // Polled by hand below: the interval is far beyond the test.
      () => useLookTryOn(['g1', 'g2'], PIECES, { refetchInterval: 1_000_000 }),
      { wrapper: wrapperFor(client) },
    );
    await waitFor(() => expect(client.isFetching()).toBe(0));
    const poll = async (answer: 'fail' | 'running') => {
      if (answer === 'fail')
        fetchMock().mockRejectedValueOnce(new TypeError('Network request failed'));
      else fetchMock().mockResolvedValueOnce(json(render({ status: 'running' })));
      await act(async () => {
        await client.refetchQueries({ queryKey: queryKeys.tryon.detail('r1') });
      });
    };
    const failures = TRYON_MAX_POLL_FAILURES;
    for (let i = 0; i < failures - 1; i++) await poll('fail');
    await waitFor(() => expect(result.current.status.phase).toBe('working'));
    // A good poll starts the count again.
    await poll('running');
    for (let i = 0; i < failures - 1; i++) await poll('fail');
    await waitFor(() => expect(result.current.status.phase).toBe('working'));
    await poll('fail');
    await waitFor(() => expect(result.current.status.phase).toBe('error'));
    await waitFor(() => expect(result.current.status.errorKind).toBe('retry'));
    // The next good poll brings the bar back.
    await poll('running');
    await waitFor(() => expect(result.current.status.phase).toBe('working'));
  });

  it('two observers of one render both show the error after too many failed polls', async () => {
    const client = makeClient();
    client.setQueryData(
      queryKeys.tryon.detail('shared'),
      render({ id: 'shared', status: 'running' }),
    );
    // Every observer mount refetches the seeded (stale) render; those polls succeed.
    fetchMock().mockImplementation(async () => json(render({ id: 'shared', status: 'running' })));
    const options = { refetchInterval: 1_000_000 };
    const first = await renderHook(() => useTryOn('shared', options), {
      wrapper: wrapperFor(client),
    });
    await waitFor(() => expect(client.isFetching()).toBe(0));
    const second = await renderHook(() => useTryOn('shared', options), {
      wrapper: wrapperFor(client),
    });
    await waitFor(() => expect(client.isFetching()).toBe(0));
    for (let i = 0; i < TRYON_MAX_POLL_FAILURES; i++) {
      fetchMock().mockRejectedValueOnce(new TypeError('Network request failed'));
      await act(async () => {
        await client.refetchQueries({ queryKey: queryKeys.tryon.detail('shared') });
      });
    }
    await waitFor(() => {
      expect(first.result.current.failedPolls).toBe(TRYON_MAX_POLL_FAILURES);
      expect(second.result.current.failedPolls).toBe(TRYON_MAX_POLL_FAILURES);
    });
  });

  it('a failed poll without a render in flight still shows the error', async () => {
    const client = makeClient();
    client.setQueryData(queryKeys.tryon.byLook('g1,g2'), { renderId: 'r1' });
    fetchMock().mockRejectedValueOnce(new TypeError('Network request failed'));
    const { result } = await renderHook(() => useLookTryOn(['g1', 'g2'], PIECES), {
      wrapper: wrapperFor(client),
    });
    await waitFor(() => expect(result.current.status.phase).toBe('error'));
  });

  it('pruning keeps the links someone observes, however old (R3-001)', async () => {
    const client = makeClient();
    const now = Date.now();
    const old = now - TRYON_MAX_AGE_MS - 1000;
    client.setQueryData(queryKeys.tryon.byLook('g1,g2'), { renderId: 'r1' }, { updatedAt: old });
    client.setQueryData(queryKeys.tryon.detail('r1'), render({ status: 'done' }));
    client.setQueryData(queryKeys.tryon.byLook('x'), { renderId: 'rx' }, { updatedAt: old });
    const { result } = await renderHook(() => useLookTryOn(['g1', 'g2'], PIECES), {
      wrapper: wrapperFor(client),
    });
    pruneTryOn(client, now);
    expect(client.getQueryData(queryKeys.tryon.byLook('g1,g2'))).toEqual({ renderId: 'r1' });
    expect(client.getQueryData(queryKeys.tryon.detail('r1'))).toBeDefined();
    expect(result.current.status.phase).toBe('done');
    // An old link nobody observes is still dropped.
    expect(client.getQueryData(queryKeys.tryon.byLook('x'))).toBeUndefined();
  });
});

describe('try-on persistence', () => {
  const query = (queryKey: readonly unknown[], data?: unknown) =>
    ({ queryKey, state: { data } }) as unknown as Parameters<typeof shouldPersistQuery>[0];

  it('keeps capabilities, links and finished renders, not renders still in flight', () => {
    expect(shouldPersistQuery(query(queryKeys.tryon.capabilities, { enabled: true }))).toBe(true);
    expect(shouldPersistQuery(query(queryKeys.tryon.byLook('a,b'), { renderId: 'r' }))).toBe(true);
    expect(shouldPersistQuery(query(queryKeys.tryon.detail('r'), { status: 'done' }))).toBe(true);
    expect(shouldPersistQuery(query(queryKeys.tryon.detail('r'), { status: 'running' }))).toBe(
      false,
    );
    expect(shouldPersistQuery(query(queryKeys.tryon.detail('r'), { status: 'failed' }))).toBe(
      false,
    );
    expect(shouldPersistQuery(query(queryKeys.tryon.detail('r')))).toBe(false);
  });

  it('prunes old links and the renders nothing points to', () => {
    const client = makeClient();
    const now = Date.now();
    const old = now - TRYON_MAX_AGE_MS - 1000;
    client.setQueryData(queryKeys.tryon.byLook('old'), { renderId: 'r-old' }, { updatedAt: old });
    client.setQueryData(queryKeys.tryon.byLook('new'), { renderId: 'r-new' });
    client.setQueryData(queryKeys.tryon.detail('r-old'), render({ id: 'r-old', status: 'done' }));
    client.setQueryData(queryKeys.tryon.detail('r-new'), render({ id: 'r-new', status: 'done' }));
    client.setQueryData(queryKeys.tryon.detail('r-orphan'), render({ status: 'done' }));
    client.setQueryData(queryKeys.tryon.capabilities, { enabled: true });

    pruneTryOn(client, now);

    expect(client.getQueryData(queryKeys.tryon.byLook('old'))).toBeUndefined();
    expect(client.getQueryData(queryKeys.tryon.byLook('new'))).toBeDefined();
    expect(client.getQueryData(queryKeys.tryon.detail('r-old'))).toBeUndefined();
    expect(client.getQueryData(queryKeys.tryon.detail('r-orphan'))).toBeUndefined();
    expect(client.getQueryData(queryKeys.tryon.detail('r-new'))).toBeDefined();
    expect(client.getQueryData(queryKeys.tryon.capabilities)).toBeDefined();
  });
});
