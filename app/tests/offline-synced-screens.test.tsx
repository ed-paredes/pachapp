import AsyncStorage from '@react-native-async-storage/async-storage';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  persistQueryClientRestore,
  persistQueryClientSave,
} from '@tanstack/react-query-persist-client';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react-native';
import { Image } from 'expo-image';
import { Platform } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { queryKeys } from '../src/api-client/query-keys';
import { ToastProvider } from '../src/components/ui';
import {
  applyPersistedDefaults,
  cacheBuster,
  createPersister,
  PERSIST_STORAGE_KEY,
  shouldPersistQuery,
} from '../src/offline/persistence';
import { resetBackendStatus } from '../src/offline/reachability';
import { syncWardrobe } from '../src/offline/sync';
import {
  ALL_STATUS,
  armarioFilters,
  countFilters,
  DEFAULT_STATUS,
  USAGE_FILTERS,
} from '../src/lib/wardrobe-filters';

jest.mock('expo-router', () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
    back: jest.fn(),
    canGoBack: () => true,
  }),
  useLocalSearchParams: () => ({ id: 'g0' }),
}));

/* eslint-disable @typescript-eslint/no-require-imports */
const DetailScreen = require('../app/garments/[id]').default;
const HistoryScreen = require('../app/(tabs)/history').default;
const TodayScreen = require('../app/(tabs)/index').default;
const WardrobeScreen = require('../app/(tabs)/wardrobe').default;
/* eslint-enable @typescript-eslint/no-require-imports */

const realOS = Platform.OS;
const realFetch = globalThis.fetch;
const json = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

// Four active garments (two worn) and one in the laundry.
const GARMENTS = [
  { id: 'g0', status: 'active', wear_count: 5 },
  { id: 'g1', status: 'active', wear_count: 3 },
  { id: 'g2', status: 'active', wear_count: 0 },
  { id: 'g3', status: 'active', wear_count: 0 },
  { id: 'g4', status: 'laundry', wear_count: 1 },
].map((garment) => ({
  category: 'top',
  subcategory: null,
  colors: null,
  is_neutral: null,
  pattern: null,
  needs_review: false,
  user_verified: false,
  img_thumb: null,
  img_cutout: null,
  last_worn_at: null,
  created_at: '2026-01-01T10:00:00Z',
  updated_at: '2026-01-01T10:00:00Z',
  job: null,
  ...garment,
}));

/** A small API that honours `status`, `sort`, `order` and paging, like the real one. */
function serveApi() {
  globalThis.fetch = jest.fn(async (input: Request | string) => {
    const url = new URL(typeof input === 'string' ? input : input.url);
    if (url.pathname === '/garments') {
      const statuses = url.searchParams.getAll('status');
      let items = GARMENTS.filter(
        (item) => statuses.length === 0 || statuses.includes(item.status),
      );
      if (url.searchParams.get('sort') === 'wear_count') {
        const sign = url.searchParams.get('order') === 'asc' ? 1 : -1;
        items = [...items].sort((a, b) => sign * (a.wear_count - b.wear_count));
      }
      const size = Number(url.searchParams.get('page_size') ?? '50');
      const page = Number(url.searchParams.get('page') ?? '1');
      return json({
        items: items.slice((page - 1) * size, page * size),
        total: items.length,
        page,
        page_size: size,
      });
    }
    if (url.pathname === '/settings') return json({ weight_color: 0.3 });
    const detail = /^\/garments\/(.+)$/.exec(url.pathname);
    if (detail) return json(GARMENTS.find((item) => item.id === detail[1]));
    return new Response('{}', { status: 404 });
  }) as unknown as typeof fetch;
}

const apiDown = () => {
  globalThis.fetch = jest.fn(() =>
    Promise.reject(new TypeError('Network request failed')),
  ) as never;
};

const clients: QueryClient[] = [];
function makeClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  applyPersistedDefaults(client);
  clients.push(client);
  return client;
}

async function renderIn(client: QueryClient, ui: React.ReactNode) {
  return render(
    <SafeAreaProvider
      initialMetrics={{
        frame: { x: 0, y: 0, width: 390, height: 844 },
        insets: { top: 24, left: 0, right: 0, bottom: 0 },
      }}
    >
      <ToastProvider>
        <QueryClientProvider client={client}>{ui}</QueryClientProvider>
      </ToastProvider>
    </SafeAreaProvider>,
  );
}

const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });

/** The three screens, rendered against `client` with the API down. */
async function expectScreensShowSyncedGarments(client: QueryClient) {
  await renderIn(client, <WardrobeScreen />);
  await settle();
  expect(screen.queryByTestId('error-state')).toBeNull();
  // The counters are separate page-size-1 requests.
  expect(screen.getByText('5 prendas · 4 activas')).toBeTruthy();
  for (const garment of GARMENTS)
    expect(screen.getByTestId(`garment-card-${garment.id}`)).toBeTruthy();
  await cleanup();

  await renderIn(client, <TodayScreen />);
  await settle();
  expect(screen.queryByTestId('error-state')).toBeNull();
  expect(screen.getByText(/Ya tienes 5 prendas en tu armario/)).toBeTruthy();
  await cleanup();

  await renderIn(client, <HistoryScreen />);
  await settle();
  expect(screen.queryByTestId('error-state')).toBeNull();
  expect(screen.getByTestId('rank-most-worn')).toBeTruthy();
  // The never-worn list comes from its own synced request.
  expect(screen.getByTestId('rank-second-chance')).toBeTruthy();
  expect(screen.getByTestId('kpi-unworn')).toHaveTextContent(/^2prendas sin estrenar/);
  await cleanup();
}

beforeEach(async () => {
  Object.defineProperty(Platform, 'OS', { configurable: true, get: () => 'android' });
  jest.spyOn(Image, 'getCachePathAsync').mockResolvedValue(null);
  jest.spyOn(Image, 'prefetch').mockResolvedValue(true);
  jest.spyOn(console, 'warn').mockImplementation(() => undefined);
  await AsyncStorage.clear();
  resetBackendStatus();
});

afterEach(async () => {
  await cleanup();
  jest.restoreAllMocks();
  globalThis.fetch = realFetch;
  Object.defineProperty(Platform, 'OS', { configurable: true, get: () => realOS });
  clients.splice(0).forEach((client) => client.clear());
  resetBackendStatus();
});

describe('screens read what the sync saved', () => {
  it('Armario, Hoy and Historial show the synced garments with the API down', async () => {
    serveApi();
    const client = makeClient();
    expect((await syncWardrobe(client)).ok).toBe(true);

    apiDown();
    await expectScreensShowSyncedGarments(client);
  });

  it('the screens and the sync build the same keys from the shared filters', () => {
    // Guards the single source of truth: a screen filter that is not in the sync would miss.
    expect(queryKeys.garments.infinite(armarioFilters({ status: DEFAULT_STATUS }))).toEqual(
      queryKeys.garments.infinite({
        status: ['active', 'laundry'],
        sort: 'created_at',
        order: 'desc',
        page_size: 50,
      }),
    );
    expect(queryKeys.garments.list(countFilters({ status: ALL_STATUS }))).toEqual(
      queryKeys.garments.list({ status: ['active', 'laundry', 'archived'], page_size: 1 }),
    );
    expect(queryKeys.garments.list(USAGE_FILTERS)).toEqual(
      queryKeys.garments.list({
        status: ['active'],
        sort: 'wear_count',
        order: 'desc',
        page_size: 200,
      }),
    );
  });

  it('Detalle shows a synced garment that was never opened, with the API down', async () => {
    serveApi();
    const client = makeClient();
    await syncWardrobe(client);

    apiDown();
    await renderIn(client, <DetailScreen />);
    await settle();
    expect(screen.queryByTestId('error-state')).toBeNull();
    expect(client.getQueryData(queryKeys.garments.detail('g0'))).toMatchObject({ id: 'g0' });
  });
});

describe('a save and restore round trip', () => {
  it('restores a query that errored offline as a success, and the screens render it', async () => {
    serveApi();
    const earlier = makeClient();
    await syncWardrobe(earlier);

    // The app opened offline: refetches fail and turn the saved queries to `error` (data kept).
    apiDown();
    await renderIn(earlier, <TodayScreen />);
    await settle();
    const usageKey = queryKeys.garments.list(USAGE_FILTERS);
    expect(earlier.getQueryState(usageKey)?.status).toBe('error');
    await cleanup();

    const persister = createPersister();
    await persistQueryClientSave({
      queryClient: earlier,
      persister,
      buster: cacheBuster(),
      dehydrateOptions: { shouldDehydrateQuery: shouldPersistQuery },
    });
    await waitFor(async () => expect(await AsyncStorage.getItem(PERSIST_STORAGE_KEY)).toBeTruthy());
    const raw = JSON.parse((await AsyncStorage.getItem(PERSIST_STORAGE_KEY)) as string) as {
      clientState: { queries: { state: { status: string; error: unknown } }[] };
    };
    expect(raw.clientState.queries.every((entry) => entry.state.status === 'success')).toBe(true);
    expect(raw.clientState.queries.every((entry) => entry.state.error === null)).toBe(true);

    const restored = makeClient();
    await persistQueryClientRestore({
      queryClient: restored,
      persister,
      buster: cacheBuster(),
    });
    const state = restored.getQueryState(usageKey);
    expect(state?.status).toBe('success');
    expect(state?.error).toBeNull();
    expect(state?.data).toBeDefined();

    await expectScreensShowSyncedGarments(restored);
  });

  it('also fixes a cache an earlier version wrote with errored queries', async () => {
    serveApi();
    const earlier = makeClient();
    await syncWardrobe(earlier);
    const usageKey = queryKeys.garments.list(USAGE_FILTERS);
    // Write the old shape by hand: the errored state exactly as it used to be saved.
    await persistQueryClientSave({
      queryClient: earlier,
      persister: {
        persistClient: (persisted) =>
          AsyncStorage.setItem(
            PERSIST_STORAGE_KEY,
            JSON.stringify({
              ...persisted,
              clientState: {
                ...persisted.clientState,
                queries: persisted.clientState.queries.map((entry) => ({
                  ...entry,
                  state: { ...entry.state, status: 'error', error: { message: 'offline' } },
                })),
              },
            }),
          ),
        restoreClient: async () => undefined,
        removeClient: async () => undefined,
      },
      buster: cacheBuster(),
      dehydrateOptions: { shouldDehydrateQuery: shouldPersistQuery },
    });

    const restored = makeClient();
    await persistQueryClientRestore({
      queryClient: restored,
      persister: createPersister(),
      buster: cacheBuster(),
    });
    expect(restored.getQueryState(usageKey)?.status).toBe('success');
  });
});
