import AsyncStorage from '@react-native-async-storage/async-storage';
import { QueryClient, useIsRestoring } from '@tanstack/react-query';
import { persistQueryClientSave } from '@tanstack/react-query-persist-client';
import { renderHook, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { Platform } from 'react-native';

import { queryKeys } from '../src/api-client/query-keys';
import { useGarments } from '../src/hooks/useGarments';
import { OfflineProvider } from '../src/offline/OfflineProvider';
import {
  applyPersistedDefaults,
  cacheBuster,
  createPersister,
  PERSIST_STORAGE_KEY,
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
  const query = (queryKey: unknown[], status = 'success') =>
    ({ queryKey, state: { status } }) as unknown as Parameters<typeof shouldPersistQuery>[0];

  it('keeps successful garment lists, infinite lists, details, settings and the sync stamp', () => {
    expect(shouldPersistQuery(query([...queryKeys.garments.list({ status: ['active'] })]))).toBe(
      true,
    );
    expect(shouldPersistQuery(query([...queryKeys.garments.infinite({})]))).toBe(true);
    expect(shouldPersistQuery(query([...queryKeys.garments.detail('g1')]))).toBe(true);
    expect(shouldPersistQuery(query([...queryKeys.settings]))).toBe(true);
    expect(shouldPersistQuery(query([...queryKeys.sync.last]))).toBe(true);
  });

  it('never keeps jobs, health or queries that are not successful', () => {
    expect(shouldPersistQuery(query([...queryKeys.jobs.detail('j1')]))).toBe(false);
    expect(shouldPersistQuery(query(['health']))).toBe(false);
    expect(shouldPersistQuery(query([...queryKeys.garments.list({})], 'error'))).toBe(false);
    expect(shouldPersistQuery(query([...queryKeys.garments.list({})], 'pending'))).toBe(false);
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
    await renderHook(() => null, { wrapper: wrapperFor(client) });

    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(client.getQueryData(queryKeys.garments.list({ status: ['active'] }))).toBeUndefined();
  });

  it('on web never reads, writes or syncs', async () => {
    setPlatform('web');
    const client = makeClient();
    await renderHook(() => null, { wrapper: wrapperFor(client) });

    client.setQueryData(queryKeys.garments.list({ status: ['active'] }), LIST);
    // Longer than the persister's 1 s write throttle.
    await new Promise((resolve) => setTimeout(resolve, 1300));

    expect(AsyncStorage.setItem).not.toHaveBeenCalled();
    expect(AsyncStorage.getItem).not.toHaveBeenCalled();
    expect(mockSync).not.toHaveBeenCalled();
  });
});
