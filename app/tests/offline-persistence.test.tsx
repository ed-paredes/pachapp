import AsyncStorage from '@react-native-async-storage/async-storage';
import { QueryClient, useIsRestoring } from '@tanstack/react-query';
import { persistQueryClientSave } from '@tanstack/react-query-persist-client';
import { renderHook, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { AppState, Platform } from 'react-native';

import { queryKeys } from '../src/api-client/query-keys';
import { useGarments } from '../src/hooks/useGarments';
import { OfflineProvider } from '../src/offline/OfflineProvider';
import {
  applyPersistedDefaults,
  cacheBuster,
  createPersister,
  PERSIST_STORAGE_KEY,
  settleQueries,
  shouldPersistQuery,
} from '../src/offline/persistence';

// The sync has its own tests; here it must not touch the network.
const mockSync = jest.fn();
jest.mock('../src/offline/sync', () => ({
  syncWardrobe: (...args: unknown[]) => mockSync(...args),
}));

const LIST = { items: [{ id: 'g1' }], total: 1, page: 1, page_size: 50 };
const realOS = Platform.OS;
const realFetch = globalThis.fetch;
const clients: QueryClient[] = [];

function makeClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  applyPersistedDefaults(client);
  clients.push(client);
  return client;
}

function setPlatform(os: string) {
  Object.defineProperty(Platform, 'OS', { configurable: true, get: () => os });
}

async function stored() {
  const raw = await AsyncStorage.getItem(PERSIST_STORAGE_KEY);
  return raw
    ? (JSON.parse(raw) as { buster: string; clientState: { queries: { queryKey: unknown[] }[] } })
    : null;
}

async function savedRoots() {
  return (await stored())?.clientState.queries.map((entry) => entry.queryKey[0]) ?? [];
}

/** Writes `client` to AsyncStorage as an earlier app run would have. */
async function saveEarlierRun(client: QueryClient, buster = cacheBuster()) {
  await persistQueryClientSave({
    queryClient: client,
    persister: createPersister(),
    buster,
    dehydrateOptions: { shouldDehydrateQuery: shouldPersistQuery },
  });
  await waitFor(async () => expect(await savedRoots()).toContain('garments'));
}

beforeEach(async () => {
  mockSync.mockResolvedValue({ ok: false, error: new Error('offline') });
  await AsyncStorage.clear();
  jest.clearAllMocks();
});

afterEach(() => {
  setPlatform(realOS);
  globalThis.fetch = realFetch;
  clients.splice(0).forEach((client) => client.clear());
});

describe('shouldPersistQuery', () => {
  const query = (queryKey: unknown[], state: { data?: unknown } = { data: {} }) =>
    ({ queryKey, state }) as unknown as Parameters<typeof shouldPersistQuery>[0];

  it('keeps successful garment lists, infinite lists, details, settings and the sync stamp', () => {
    expect(shouldPersistQuery(query([...queryKeys.garments.list({ status: ['active'] })]))).toBe(
      true,
    );
    expect(shouldPersistQuery(query([...queryKeys.garments.infinite({})]))).toBe(true);
    expect(shouldPersistQuery(query([...queryKeys.garments.detail('g1')]))).toBe(true);
    expect(shouldPersistQuery(query([...queryKeys.settings]))).toBe(true);
    expect(shouldPersistQuery(query([...queryKeys.sync.last]))).toBe(true);
  });

  it('never keeps jobs, health or queries without data', () => {
    expect(shouldPersistQuery(query([...queryKeys.jobs.detail('j1')]))).toBe(false);
    expect(shouldPersistQuery(query(['health']))).toBe(false);
    // Nothing to save yet (pending or failed before any data).
    expect(shouldPersistQuery(query([...queryKeys.garments.list({})], { data: undefined }))).toBe(
      false,
    );
  });
});

describe('a failed refetch', () => {
  it('keeps the saved data on disk: it must not wipe the offline copy', async () => {
    setPlatform('android');
    const client = makeClient();
    const key = queryKeys.garments.list({ status: ['active'] });
    client.setQueryData(key, LIST);
    // Offline refetch: the query turns to `error` but keeps its data.
    globalThis.fetch = jest.fn(() => Promise.reject(new TypeError('Network request failed')));
    await client
      .fetchQuery({ queryKey: key, queryFn: () => Promise.reject(new TypeError('x')) })
      .catch(() => undefined);
    expect(client.getQueryState(key)?.status).toBe('error');

    const query = client.getQueryCache().find({ queryKey: key });
    expect(query && shouldPersistQuery(query)).toBe(true);
  });
});

describe('applyPersistedDefaults', () => {
  it('keeps persisted families in memory at least as long as they stay valid on disk', () => {
    const client = makeClient();
    // Not 30 days: a timer above ~24.8 days overflows and fires at once, dropping the query.
    expect(client.getQueryDefaults(queryKeys.garments.list({})).gcTime).toBe(Infinity);
    expect(client.getQueryDefaults(queryKeys.settings).gcTime).toBe(Infinity);
    expect(client.getQueryDefaults(queryKeys.jobs.detail('j1')).gcTime).toBeUndefined();
  });
});

describe('OfflineProvider', () => {
  const wrapperFor = (client: QueryClient) =>
    function Wrapper({ children }: { children: ReactNode }) {
      return <OfflineProvider client={client}>{children}</OfflineProvider>;
    };

  it('on native saves the allowed families and leaves jobs out', async () => {
    setPlatform('android');
    const client = makeClient();
    const { result } = await renderHook(() => useIsRestoring(), { wrapper: wrapperFor(client) });
    // Changes are saved once the saved copy has been restored (the sync starts then too).
    await waitFor(() => expect(result.current).toBe(false));

    client.setQueryData(queryKeys.garments.list({ status: ['active'] }), LIST);
    client.setQueryData(queryKeys.garments.detail('g1'), { id: 'g1' });
    client.setQueryData(queryKeys.jobs.detail('j1'), { id: 'j1', status: 'running' });

    await waitFor(async () => expect(await savedRoots()).toContain('garments'));
    expect(await savedRoots()).not.toContain('jobs');
    expect((await stored())?.buster).toBe(cacheBuster());
  });

  it('on native syncs the wardrobe once the saved copy is back', async () => {
    setPlatform('android');
    await renderHook(() => null, { wrapper: wrapperFor(makeClient()) });
    await waitFor(() => expect(mockSync).toHaveBeenCalledTimes(1));
  });

  it('on native shows the saved garments while the API is unreachable', async () => {
    setPlatform('android');
    const earlier = makeClient();
    earlier.setQueryData(queryKeys.garments.list({ status: ['active'] }), LIST);
    await saveEarlierRun(earlier);

    globalThis.fetch = jest.fn(() => Promise.reject(new TypeError('Network request failed')));
    const { result } = await renderHook(() => useGarments({ status: ['active'] }), {
      wrapper: wrapperFor(makeClient()),
    });

    await waitFor(() => expect(result.current.data).toEqual(LIST));
  });

  it('on native ignores a cache written by another app version', async () => {
    setPlatform('android');
    const earlier = makeClient();
    earlier.setQueryData(queryKeys.garments.list({ status: ['active'] }), LIST);
    await saveEarlierRun(earlier, '0.0.1:0');

    globalThis.fetch = jest.fn(() => Promise.reject(new TypeError('Network request failed')));
    const client = makeClient();
    const { result } = await renderHook(() => useIsRestoring(), { wrapper: wrapperFor(client) });

    // The restore has run (the buster check is part of it) and found nothing usable.
    await waitFor(() => expect(result.current).toBe(false));
    expect(AsyncStorage.getItem).toHaveBeenCalledWith(PERSIST_STORAGE_KEY);
    expect(client.getQueryData(queryKeys.garments.list({ status: ['active'] }))).toBeUndefined();
  });

  it('on web never reads, writes or syncs', async () => {
    setPlatform('web');
    const client = makeClient();
    await renderHook(() => null, { wrapper: wrapperFor(client) });

    // A marker only this web client holds: a throttled write left over from an earlier native
    // test cannot carry it, so the assertion below cannot be tripped by test order.
    client.setQueryData(queryKeys.garments.list({ status: ['active'] }), {
      ...LIST,
      items: [{ id: 'web-only-marker' }],
    });
    // Longer than the persister's 1 s write throttle.
    await new Promise((resolve) => setTimeout(resolve, 1300));

    const writes = (AsyncStorage.setItem as jest.Mock).mock.calls.map(([, value]) => String(value));
    expect(writes.some((value) => value.includes('web-only-marker'))).toBe(false);
    expect(AsyncStorage.getItem).not.toHaveBeenCalled();
    expect(mockSync).not.toHaveBeenCalled();
  });
});

describe('saving the cache', () => {
  const warn = () => jest.spyOn(console, 'warn').mockImplementation(() => undefined);

  async function save(client: QueryClient) {
    await persistQueryClientSave({
      queryClient: client,
      persister: createPersister(),
      buster: cacheBuster(),
      dehydrateOptions: { shouldDehydrateQuery: shouldPersistQuery },
    });
  }

  function fullClient() {
    const client = makeClient();
    client.setQueryData(queryKeys.garments.list({ status: ['active'] }), LIST);
    client.setQueryData(queryKeys.garments.detail('g1'), { id: 'g1' });
    client.setQueryData(queryKeys.sync.last, 1);
    return client;
  }

  it('logs a failed write and retries once without the garment details', async () => {
    const logged = warn();
    jest.spyOn(AsyncStorage, 'setItem').mockRejectedValueOnce(new Error('Row too big'));

    await save(fullClient());

    await waitFor(async () => expect(await savedRoots()).toContain('garments'));
    expect(logged).toHaveBeenCalledWith(expect.stringContaining('Row too big'));
    const kinds = (await stored())?.clientState.queries.map((entry) => entry.queryKey[1]);
    expect(kinds).toContain('list');
    expect(kinds).not.toContain('detail');
  });

  it('gives up quietly when the lean copy fails too, keeping the previous copy', async () => {
    const earlier = makeClient();
    earlier.setQueryData(queryKeys.garments.list({ status: ['laundry'] }), LIST);
    await saveEarlierRun(earlier);
    const logged = warn();
    jest
      .spyOn(AsyncStorage, 'setItem')
      .mockRejectedValueOnce(new Error('disk full'))
      .mockRejectedValueOnce(new Error('disk full'));

    await expect(save(fullClient())).resolves.toBeUndefined();

    // The persister starts the write without awaiting it: wait for both attempts to be logged.
    await waitFor(() => expect(logged).toHaveBeenCalledTimes(2));
    const entries = (await stored())?.clientState.queries ?? [];
    expect(entries).toHaveLength(1);
    expect(entries[0].queryKey[2]).toEqual({ status: ['laundry'] });
  });

  it('settleQueries turns errored and fetching queries into finished successes', () => {
    const query = (state: object) => ({ queryKey: ['garments'], queryHash: 'h', state });
    const settled = settleQueries({
      timestamp: 1,
      buster: 'b',
      clientState: {
        mutations: [],
        queries: [
          query({
            data: LIST,
            status: 'error',
            fetchStatus: 'fetching',
            error: new Error('x'),
            errorUpdatedAt: 5,
            errorUpdateCount: 2,
            fetchFailureCount: 3,
            fetchFailureReason: new Error('x'),
            dataUpdatedAt: 7,
          }),
        ],
      },
    } as never);
    expect(settled.clientState.queries[0].state).toMatchObject({
      data: LIST,
      dataUpdatedAt: 7,
      status: 'success',
      fetchStatus: 'idle',
      error: null,
      errorUpdatedAt: 0,
      fetchFailureCount: 0,
      fetchFailureReason: null,
    });
  });

  it('settleQueries drops entries without data instead of restoring them as empty successes', () => {
    const query = (key: string, state: object) => ({ queryKey: [key], queryHash: key, state });
    const settled = settleQueries({
      timestamp: 1,
      buster: 'b',
      clientState: {
        mutations: [],
        queries: [
          query('kept', { data: LIST, status: 'success' }),
          query('errored', { data: undefined, status: 'error', error: new Error('x') }),
          query('pending', { data: undefined, status: 'pending' }),
        ],
      },
    } as never);
    expect(settled.clientState.queries.map((entry) => entry.queryHash)).toEqual(['kept']);
  });
});

describe('WardrobeSyncer foreground re-sync', () => {
  const remove = jest.fn();
  let fire: (state: string) => void;

  beforeEach(() => {
    setPlatform('android');
    remove.mockClear();
    jest.spyOn(AppState, 'addEventListener').mockImplementation(((
      _type: string,
      handler: (state: string) => void,
    ) => {
      fire = handler;
      return { remove };
    }) as never);
  });

  const wrapper = (client: QueryClient) =>
    function Wrapper({ children }: { children: ReactNode }) {
      return <OfflineProvider client={client}>{children}</OfflineProvider>;
    };

  const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

  it('does not sync again on foreground after a successful run', async () => {
    mockSync.mockResolvedValue({ ok: true, syncedAt: 1 });
    await renderHook(() => null, { wrapper: wrapper(makeClient()) });
    await waitFor(() => expect(mockSync).toHaveBeenCalledTimes(1));
    await flush();

    fire('active');
    await flush();
    expect(mockSync).toHaveBeenCalledTimes(1);
  });

  it('syncs again on foreground after a failed run, and stops once one succeeds', async () => {
    mockSync.mockResolvedValueOnce({ ok: false, error: new Error('offline') });
    mockSync.mockResolvedValue({ ok: true, syncedAt: 1 });
    await renderHook(() => null, { wrapper: wrapper(makeClient()) });
    await waitFor(() => expect(mockSync).toHaveBeenCalledTimes(1));
    await flush();

    fire('background');
    await flush();
    expect(mockSync).toHaveBeenCalledTimes(1);

    fire('active');
    await waitFor(() => expect(mockSync).toHaveBeenCalledTimes(2));
    await flush();

    fire('active');
    await flush();
    expect(mockSync).toHaveBeenCalledTimes(2);
  });

  it('removes its AppState subscription when it unmounts', async () => {
    const { unmount } = await renderHook(() => null, { wrapper: wrapper(makeClient()) });
    await waitFor(() => expect(mockSync).toHaveBeenCalled());
    const added = (AppState.addEventListener as jest.Mock).mock.calls.length;
    expect(added).toBeGreaterThan(0);
    expect(remove).not.toHaveBeenCalled();

    await unmount();
    // The syncer and the reconnect watcher each subscribe; every subscription is removed.
    expect(remove).toHaveBeenCalledTimes(added);
  });
});
