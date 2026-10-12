import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { act, cleanup, render, renderHook, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { Platform } from 'react-native';

import { DEFAULT_STALE_TIME_MS, queryClient } from '../src/api-client/query-client';
import { queryKeys } from '../src/api-client/query-keys';
import { usePatchGarment } from '../src/hooks/useGarmentMutations';
import {
  GARMENT_SUMMARY_STALE_MS,
  GARMENTS_POLL_INTERVAL_MS,
  useGarments,
  useInfiniteGarments,
} from '../src/hooks/useGarments';
import { useJob } from '../src/hooks/useJob';
import { OfflineProvider } from '../src/offline/OfflineProvider';
import {
  reportReachable,
  reportUnreachable,
  resetBackendStatus,
} from '../src/offline/reachability';

const mockSync = jest.fn();
jest.mock('../src/offline/sync', () => ({
  syncWardrobe: (...args: unknown[]) => mockSync(...args),
}));

const clients: QueryClient[] = [];

/** Same defaults as the app client (30 s fresh window), without timers outliving the test. */
function makeClient() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity, staleTime: DEFAULT_STALE_TIME_MS },
      mutations: { gcTime: 0 },
    },
  });
  clients.push(client);
  return client;
}

const wrapperFor = (client: QueryClient) =>
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const page = (items: unknown[] = []) => ({ items, total: items.length, page: 1, page_size: 50 });
const fetchMock = () => globalThis.fetch as jest.Mock;

const realFetch = globalThis.fetch;
const realOS = Platform.OS;
const setPlatform = (os: string) =>
  Object.defineProperty(Platform, 'OS', { configurable: true, get: () => os });

beforeEach(() => {
  globalThis.fetch = jest.fn();
  mockSync.mockResolvedValue({ ok: true, syncedAt: 1 });
  setPlatform('android');
  resetBackendStatus();
});

afterEach(async () => {
  await cleanup();
  jest.useRealTimers();
  clients.splice(0).forEach((client) => client.clear());
  globalThis.fetch = realFetch;
  setPlatform(realOS);
  resetBackendStatus();
  jest.clearAllMocks();
});

describe('query client defaults', () => {
  it('keeps fetched data fresh for 30 s and still does not retry', () => {
    const defaults = queryClient.getDefaultOptions().queries;
    expect(DEFAULT_STALE_TIME_MS).toBe(30_000);
    expect(defaults?.staleTime).toBe(30_000);
    expect(defaults?.retry).toBe(false);
  });

  it('keeps the summary lists fresher than the default window', () => {
    expect(GARMENT_SUMMARY_STALE_MS).toBeGreaterThan(DEFAULT_STALE_TIME_MS);
  });

  it('lets a summary list opt into the longer window', async () => {
    const client = makeClient();
    fetchMock().mockResolvedValue(json(page()));
    await renderHook(() => useGarments({ page_size: 1 }, { staleTime: GARMENT_SUMMARY_STALE_MS }), {
      wrapper: wrapperFor(client),
    });
    await waitFor(() => expect(fetchMock()).toHaveBeenCalledTimes(1));
    const query = client
      .getQueryCache()
      .find({ queryKey: queryKeys.garments.list({ page_size: 1 }) });
    expect(query?.observers[0]?.options.staleTime).toBe(GARMENT_SUMMARY_STALE_MS);
  });
});

describe('polling with the default staleTime', () => {
  it('useInfiniteGarments keeps polling while a garment is processing', async () => {
    jest.useFakeTimers();
    const processing = { id: 'g1', job: { status: 'running' } };
    fetchMock().mockImplementation(async () => json(page([processing])));
    await renderHook(() => useInfiniteGarments({ page_size: 50 }), {
      wrapper: wrapperFor(makeClient()),
    });
    await act(async () => {
      await jest.advanceTimersByTimeAsync(0);
    });
    const first = fetchMock().mock.calls.length;
    expect(first).toBeGreaterThanOrEqual(1);

    await act(async () => {
      await jest.advanceTimersByTimeAsync(GARMENTS_POLL_INTERVAL_MS * 3 + 10);
    });
    expect(fetchMock().mock.calls.length).toBe(first + 3);
  });

  it('useJob keeps polling until the job is done', async () => {
    const job = (status: string) =>
      json({ status, step: 'cutout', progress: 10, error: null, result: null });
    fetchMock()
      .mockResolvedValueOnce(job('running'))
      .mockResolvedValueOnce(job('running'))
      .mockResolvedValueOnce(job('done'));
    const { result } = await renderHook(() => useJob('j1', { refetchInterval: 10 }), {
      wrapper: wrapperFor(makeClient()),
    });
    await waitFor(() => expect(result.current.data?.status).toBe('done'));
    expect(fetchMock()).toHaveBeenCalledTimes(3);
  });
});

describe('mutations still refresh fresh data', () => {
  it('a patch refetches a list that is still inside the fresh window', async () => {
    const client = makeClient();
    fetchMock().mockImplementation(async (request: Request) =>
      request.method === 'PATCH' ? json({ id: 'g1' }) : json(page()),
    );
    await renderHook(
      () => ({ list: useGarments({ page_size: 1 }), patch: usePatchGarment('g1') }),
      { wrapper: wrapperFor(client) },
    );
    await waitFor(() => expect(fetchMock()).toHaveBeenCalledTimes(1));

    // Still fresh: remounting would not fetch. The mutation must.
    const { result } = await renderHook(() => usePatchGarment('g1'), {
      wrapper: wrapperFor(client),
    });
    await act(async () => {
      await result.current.mutateAsync({ category: 'top' });
    });
    await waitFor(() => {
      const gets = fetchMock().mock.calls.filter(([r]) => (r as Request).method === 'GET');
      expect(gets).toHaveLength(2);
    });
  });
});

describe('ReconnectWatcher', () => {
  const freshFn = jest.fn(async () => 'fresh');
  const staleFn = jest.fn(async () => 'stale');

  function Screens() {
    useQuery({ queryKey: ['fresh'], queryFn: freshFn });
    useQuery({ queryKey: ['stale'], queryFn: staleFn, staleTime: 0 });
    return null;
  }

  async function mountOnline(client: QueryClient) {
    reportReachable();
    globalThis.fetch = jest.fn(async () => json({ status: 'ok' }));
    await render(
      <QueryClientProvider client={client}>
        <OfflineProvider client={client}>
          <Screens />
        </OfflineProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(staleFn).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(freshFn).toHaveBeenCalledTimes(1));
    mockSync.mockClear();
  }

  const flap = () =>
    act(async () => {
      reportUnreachable();
      reportReachable();
      // Lets the refetches land inside `act`, so no update leaks past the test.
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

  it('refetches the stale active query and leaves the fresh one alone', async () => {
    const client = makeClient();
    await mountOnline(client);

    await flap();

    await waitFor(() => expect(staleFn).toHaveBeenCalledTimes(2));
    expect(freshFn).toHaveBeenCalledTimes(1);
  });

  it('a flap within the window does not refetch a fresh list, however often it repeats', async () => {
    const client = makeClient();
    await mountOnline(client);

    await flap();
    await flap();
    await flap();

    expect(freshFn).toHaveBeenCalledTimes(1);
  });

  it('syncs the wardrobe after a reconnect unless it just synced', async () => {
    const client = makeClient();
    await mountOnline(client);

    client.setQueryData(queryKeys.sync.last, Date.now() - DEFAULT_STALE_TIME_MS - 1000);
    await flap();
    expect(mockSync).toHaveBeenCalledTimes(1);

    client.setQueryData(queryKeys.sync.last, Date.now());
    await flap();
    expect(mockSync).toHaveBeenCalledTimes(1);
  });
});
