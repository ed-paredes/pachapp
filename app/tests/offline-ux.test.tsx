import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { AccessibilityInfo, Platform } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { apiClient } from '../src/api-client/http-client';
import { queryKeys } from '../src/api-client/query-keys';
import { UploadZone } from '../src/components/add/UploadZone';
import { OFFLINE_NOTE, OfflineChrome, offlineBannerText } from '../src/components/OfflineBanner';
import { ToastProvider } from '../src/components/ui';
import { OfflineProvider, RECONNECT_INTERVAL_MS } from '../src/offline/OfflineProvider';
import {
  getBackendStatus,
  reportReachable,
  reportUnreachable,
  resetBackendStatus,
} from '../src/offline/reachability';

const mockSync = jest.fn();
jest.mock('../src/offline/sync', () => ({
  syncWardrobe: (...args: unknown[]) => mockSync(...args),
}));

const mockPush = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: jest.fn(),
    back: jest.fn(),
    canGoBack: () => true,
  }),
  useLocalSearchParams: () => ({ id: 'g1' }),
}));

/* eslint-disable @typescript-eslint/no-require-imports */
const DetailScreen = require('../app/garments/[id]').default;
const ReviewScreen = require('../app/review/[id]').default;
const TodayScreen = require('../app/(tabs)/index').default;
const WardrobeScreen = require('../app/(tabs)/wardrobe').default;
const SettingsScreen = require('../app/settings').default;
/* eslint-enable @typescript-eslint/no-require-imports */

const DAY_MS = 24 * 60 * 60 * 1000;
const realOS = Platform.OS;
const realFetch = globalThis.fetch;
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const setPlatform = (os: string) =>
  Object.defineProperty(Platform, 'OS', { configurable: true, get: () => os });
const networkDown = (): jest.Mock =>
  jest.fn(() => Promise.reject(new TypeError('Network request failed')));

const GARMENT = {
  id: 'g1',
  category: 'mid_layer',
  subcategory: 'jersey',
  colors: [{ name: 'marino', hex: '#141e50', lab: [12, 5, -20], proportion: 1 }],
  is_neutral: true,
  pattern: 'striped',
  status: 'active',
  needs_review: false,
  user_verified: true,
  img_thumb: 'thumb/g1.webp',
  img_cutout: 'cutout/g1.png',
  img_original: 'original/g1.jpg',
  wear_count: 7,
  last_worn_at: null,
  created_at: '2026-09-30T10:00:00Z',
  updated_at: '2026-09-30T10:00:00Z',
  job: { id: 'j1', status: 'done', step: null, progress: 100, error: null },
  color_confidence: 0.9,
  ai_confidence: null,
  formality: 3,
  style_tags: ['classic'],
  seasons: ['autumn', 'winter'],
  warmth: 4,
  material: 'lana',
  brand: null,
  notes: null,
  outfit_count: 5,
};

const SETTINGS = {
  weight_color: 0.3,
  weight_style: 0.3,
  weight_novelty: 0.2,
  weight_preference: 0.2,
  no_repeat_days: 7,
  max_accessories: 2,
  duplicate_warning_threshold: 0.9,
  needs_review_threshold: 0.7,
  color_review_threshold: 0.6,
};

const clients: QueryClient[] = [];
function makeClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { gcTime: 0 } },
  });
  clients.push(client);
  return client;
}

const seedLastSync = (client: QueryClient, at = Date.now() - 5 * DAY_MS) =>
  client.setQueryData(queryKeys.sync.last, at);

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

/** Waits until the failed refetch has landed, so the assertions below see the error state. */
/** Lets pending refetches land inside `act`, so no update leaks past the test. */
const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

async function refetchFailed(client: QueryClient, key: readonly unknown[]) {
  await waitFor(() => expect(client.getQueryState(key)?.status).toBe('error'));
  // Let React render the error state before the screen is inspected.
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

beforeEach(() => {
  mockSync.mockResolvedValue({ ok: true, syncedAt: 1 });
  jest.spyOn(AccessibilityInfo, 'announceForAccessibility').mockImplementation(() => undefined);
  setPlatform('android');
  resetBackendStatus();
});

afterEach(() => {
  cleanup();
  jest.useRealTimers();
  jest.restoreAllMocks();
  globalThis.fetch = realFetch;
  setPlatform(realOS);
  resetBackendStatus();
  clients.splice(0).forEach((client) => client.clear());
  jest.clearAllMocks();
});

describe('backend reachability', () => {
  it('a network failure marks the backend offline', async () => {
    globalThis.fetch = networkDown();
    await apiClient.GET('/health').catch(() => undefined);
    expect(getBackendStatus()).toBe('offline');
  });

  it('an HTTP 500 is an answer, so the backend is not offline', async () => {
    globalThis.fetch = jest.fn(async () => json({ error: { code: 'X', message: 'boom' } }, 500));
    await apiClient.GET('/health');
    expect(getBackendStatus()).toBe('online');
  });

  it('a 4xx is not offline either', async () => {
    globalThis.fetch = jest.fn(async () => json({ error: { code: 'X', message: 'no' } }, 404));
    await apiClient.GET('/health');
    expect(getBackendStatus()).toBe('online');
  });

  it('any success brings it back online', async () => {
    reportUnreachable();
    globalThis.fetch = jest.fn(async () => json({ status: 'ok' }));
    await apiClient.GET('/health');
    expect(getBackendStatus()).toBe('online');
  });

  it('a read that gets no answer for 15 s counts as unreachable', async () => {
    jest.useFakeTimers();
    globalThis.fetch = jest.fn(
      (request: Request) =>
        new Promise((_resolve, reject) => {
          request.signal.addEventListener('abort', () => reject(new Error('aborted')));
        }),
    ) as jest.Mock;
    const pending = apiClient.GET('/health').catch(() => undefined);
    await jest.advanceTimersByTimeAsync(15000);
    await pending;
    expect(getBackendStatus()).toBe('offline');
  });
});

describe('offline banner', () => {
  const app = () => (
    <OfflineChrome>
      <></>
    </OfflineChrome>
  );

  it('says the backend is unreachable and how old the saved data is', async () => {
    const client = makeClient();
    seedLastSync(client);
    reportUnreachable();
    await renderIn(client, app());

    const text = screen.getByTestId('offline-banner');
    expect(text).toHaveTextContent(
      /^Sin conexión con tu armario\. Mostrando lo guardado el \d+ \w+\.$/,
    );
  });

  it('formats the saved date', () => {
    const now = new Date(2026, 9, 6, 9, 0);
    expect(offlineBannerText(new Date(2026, 9, 4, 20, 0).getTime(), now)).toBe(
      'Sin conexión con tu armario. Mostrando lo guardado el 4 oct.',
    );
    expect(offlineBannerText(new Date(2026, 9, 6, 1, 0).getTime(), now)).toContain('guardado hoy.');
    expect(offlineBannerText(new Date(2025, 11, 31).getTime(), now)).toContain('el 31 dic 2025.');
  });

  it('is not shown while the backend answers', async () => {
    const client = makeClient();
    seedLastSync(client);
    reportReachable();
    await renderIn(client, app());
    expect(screen.queryByTestId('offline-banner')).toBeNull();
  });

  it('is not shown when nothing was ever saved: the screens keep their own error states', async () => {
    reportUnreachable();
    await renderIn(makeClient(), app());
    expect(screen.queryByTestId('offline-banner')).toBeNull();
  });

  it('never appears on web', async () => {
    setPlatform('web');
    const client = makeClient();
    seedLastSync(client);
    reportUnreachable();
    await renderIn(client, app());
    expect(screen.queryByTestId('offline-banner')).toBeNull();
  });

  it('appears and clears without a restart', async () => {
    const client = makeClient();
    seedLastSync(client);
    await renderIn(client, app());
    expect(screen.queryByTestId('offline-banner')).toBeNull();

    await act(async () => reportUnreachable());
    expect(screen.getByTestId('offline-banner')).toBeTruthy();

    await act(async () => reportReachable());
    expect(screen.queryByTestId('offline-banner')).toBeNull();
  });

  it('is announced once, not on every render', async () => {
    const client = makeClient();
    seedLastSync(client);
    reportUnreachable();
    await renderIn(client, app());
    // A newer sync stamp rewrites the date in the banner: still no second announcement.
    const newer = Date.now() - 2 * DAY_MS;
    await act(async () => seedLastSync(client, newer));
    await waitFor(() =>
      expect(screen.getByTestId('offline-banner')).toHaveTextContent(offlineBannerText(newer)),
    );
    expect(AccessibilityInfo.announceForAccessibility).toHaveBeenCalledTimes(1);
  });
});

describe('screens while the backend is unreachable', () => {
  it('Detalle shows the saved garment and turns its changes off with a reason', async () => {
    const client = makeClient();
    client.setQueryData(queryKeys.garments.detail('g1'), GARMENT);
    globalThis.fetch = networkDown();
    reportUnreachable();
    await renderIn(client, <DetailScreen />);

    // The refetch fails, but the saved garment stays on screen: no full-screen error.
    await refetchFailed(client, queryKeys.garments.detail('g1'));
    expect(screen.queryByTestId('error-state')).toBeNull();
    expect(screen.getByLabelText('Marcar como lavando').props.accessibilityState.disabled).toBe(
      true,
    );
    expect(screen.getByLabelText('Archivar').props.accessibilityState.disabled).toBe(true);
    expect(screen.getByLabelText('Eliminar prenda').props.accessibilityState.disabled).toBe(true);
    expect(screen.getByText(OFFLINE_NOTE)).toBeTruthy();
    // Looking is still possible: Revisar opens the saved garment.
    expect(screen.getByLabelText('Revisar').props.accessibilityState.disabled).toBeFalsy();
  });

  it('Detalle keeps its changes on when the backend answers', async () => {
    const client = makeClient();
    client.setQueryData(queryKeys.garments.detail('g1'), GARMENT);
    globalThis.fetch = jest.fn(async () => json(GARMENT));
    reportReachable();
    await renderIn(client, <DetailScreen />);

    await settle();
    expect(screen.getByLabelText('Archivar').props.accessibilityState.disabled).toBe(false);
    expect(screen.queryByText(OFFLINE_NOTE)).toBeNull();
  });

  it('Detalle closes an open delete confirmation when the backend goes away, and sends nothing', async () => {
    const client = makeClient();
    client.setQueryData(queryKeys.garments.detail('g1'), GARMENT);
    const fetchMock = jest.fn(async () => json(GARMENT));
    globalThis.fetch = fetchMock;
    reportReachable();
    await renderIn(client, <DetailScreen />);
    await settle();

    await fireEvent.press(screen.getByLabelText('Eliminar prenda'));
    expect(screen.getByTestId('delete-confirm')).toBeTruthy();
    fetchMock.mockClear();

    await act(async () => reportUnreachable());

    expect(screen.queryByTestId('delete-confirm')).toBeNull();
    expect(screen.queryByLabelText('Eliminar definitivamente')).toBeNull();
    expect(screen.getByText(OFFLINE_NOTE)).toBeTruthy();
    expect(screen.getByLabelText('Eliminar prenda').props.accessibilityState.disabled).toBe(true);
    expect(
      (fetchMock.mock.calls as unknown as [Request][]).filter(
        ([request]) => request.method === 'DELETE',
      ),
    ).toHaveLength(0);

    // Back online the confirmation does not reopen by itself.
    await act(async () => reportReachable());
    expect(screen.queryByTestId('delete-confirm')).toBeNull();
  });

  it('Detalle on web ignores the offline state entirely', async () => {
    setPlatform('web');
    const client = makeClient();
    client.setQueryData(queryKeys.garments.detail('g1'), GARMENT);
    globalThis.fetch = networkDown();
    reportUnreachable();
    await renderIn(client, <DetailScreen />);

    await settle();
    expect(screen.getByLabelText('Archivar').props.accessibilityState.disabled).toBe(false);
    expect(screen.queryByText(OFFLINE_NOTE)).toBeNull();
  });

  it('Revisión refuses to save a change and says why', async () => {
    const client = makeClient();
    client.setQueryData(queryKeys.garments.detail('g1'), GARMENT);
    client.setQueryData(queryKeys.settings, SETTINGS);
    const fetchMock = networkDown();
    globalThis.fetch = fetchMock;
    reportUnreachable();
    await renderIn(client, <ReviewScreen />);
    await waitFor(() => expect(screen.getByLabelText('Revisión terminada')).toBeTruthy());
    fetchMock.mockClear();

    expect(screen.getByLabelText('Revisión terminada').props.accessibilityState.disabled).toBe(
      true,
    );
    expect(screen.getByText(OFFLINE_NOTE)).toBeTruthy();

    await fireEvent.press(screen.getByLabelText(/^Formalidad,/));
    await fireEvent.press(screen.getByLabelText('Formalidad: 4'));
    expect(
      await screen.findByText('Sin conexión: este cambio no se puede guardar ahora.'),
    ).toBeTruthy();
    // Nothing was sent.
    expect(
      (fetchMock.mock.calls as [Request][]).filter(([request]) => request.method !== 'GET'),
    ).toHaveLength(0);
  });

  it('Ajustes keeps the saved form instead of an error, with Guardar off', async () => {
    const client = makeClient();
    client.setQueryData(queryKeys.settings, SETTINGS);
    globalThis.fetch = networkDown();
    reportUnreachable();
    await renderIn(client, <SettingsScreen />);

    await refetchFailed(client, queryKeys.settings);
    expect(screen.getByLabelText('Guardar').props.accessibilityState.disabled).toBe(true);
    expect(screen.getByText(OFFLINE_NOTE)).toBeTruthy();
    expect(screen.queryByText('No se pudieron cargar los ajustes.')).toBeNull();
  });

  it('Añadir turns the photo buttons off and says why', async () => {
    reportUnreachable();
    await renderIn(makeClient(), <UploadZone onCamera={jest.fn()} onGallery={jest.fn()} />);

    expect(screen.getByLabelText('Hacer foto').props.accessibilityState.disabled).toBe(true);
    expect(screen.getByLabelText('Elegir de la galería').props.accessibilityState.disabled).toBe(
      true,
    );
    expect(screen.getByText(OFFLINE_NOTE)).toBeTruthy();
  });

  it('Hoy keeps the saved wardrobe figures when the refresh fails', async () => {
    const client = makeClient();
    client.setQueryData(queryKeys.garments.list({ status: ['laundry'], page_size: 2 }), {
      items: [],
      total: 0,
      page: 1,
      page_size: 2,
    });
    client.setQueryData(
      queryKeys.garments.list({
        status: ['active'],
        sort: 'wear_count',
        order: 'desc',
        page_size: 200,
      }),
      { items: [], total: 12, page: 1, page_size: 200 },
    );
    globalThis.fetch = networkDown();
    reportUnreachable();
    await renderIn(client, <TodayScreen />);

    await refetchFailed(client, queryKeys.garments.list({ status: ['laundry'], page_size: 2 }));
    // 12 saved garments: Hoy renders from the saved lists, with no look saved yet to show.
    expect(screen.getByTestId('problem-state')).toBeTruthy();
    expect(screen.getByText('Aún no hay un look guardado')).toBeTruthy();
    expect(screen.queryByTestId('empty-state')).toBeNull();
  });

  it('Armario shows the saved grid and no second warning for the failed refresh', async () => {
    const client = makeClient();
    const filters: Parameters<typeof queryKeys.garments.infinite>[0] = {
      status: ['active', 'laundry'],
      sort: 'created_at',
      order: 'desc',
      page_size: 50,
    };
    client.setQueryData(queryKeys.garments.infinite(filters), {
      pages: [
        {
          items: [
            {
              id: 'g1',
              category: 'top',
              subcategory: null,
              colors: null,
              is_neutral: null,
              pattern: null,
              status: 'active',
              needs_review: false,
              user_verified: false,
              img_thumb: null,
              img_cutout: null,
              wear_count: 0,
              last_worn_at: null,
              created_at: '2026-01-01T10:00:00Z',
              job: null,
            },
          ],
          total: 1,
          page: 1,
          page_size: 50,
        },
      ],
      pageParams: [1],
    });
    globalThis.fetch = networkDown();
    reportUnreachable();
    await renderIn(client, <WardrobeScreen />);

    await refetchFailed(client, queryKeys.garments.infinite(filters));
    expect(screen.queryByTestId('error-state')).toBeNull();
    expect(screen.queryByTestId('wardrobe-soft-error')).toBeNull();
    expect(screen.getByTestId('wardrobe-list')).toBeTruthy();
  });
});

describe('recovering', () => {
  it('pings while offline; the first answer refreshes the screens and syncs again', async () => {
    jest.useFakeTimers();
    const client = makeClient();
    const refetch = jest.spyOn(client, 'refetchQueries');
    reportUnreachable();
    globalThis.fetch = jest.fn(async () => json({ status: 'ok' }));
    await renderIn(
      client,
      <OfflineProvider client={client}>
        <></>
      </OfflineProvider>,
    );
    mockSync.mockClear();

    await act(async () => {
      await jest.advanceTimersByTimeAsync(RECONNECT_INTERVAL_MS + 10);
    });

    expect(getBackendStatus()).toBe('online');
    expect(refetch).toHaveBeenCalledWith({ type: 'active', stale: true });
    expect(mockSync).toHaveBeenCalledTimes(1);
  });

  it('keeps quiet while the backend answers', async () => {
    jest.useFakeTimers();
    const client = makeClient();
    reportReachable();
    globalThis.fetch = jest.fn(async () => json({ status: 'ok' }));
    await renderIn(
      client,
      <OfflineProvider client={client}>
        <></>
      </OfflineProvider>,
    );
    (globalThis.fetch as jest.Mock).mockClear();

    await act(async () => {
      await jest.advanceTimersByTimeAsync(RECONNECT_INTERVAL_MS * 3);
    });
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('keeps pinging while the backend stays down', async () => {
    jest.useFakeTimers();
    const client = makeClient();
    reportUnreachable();
    globalThis.fetch = networkDown();
    await renderIn(
      client,
      <OfflineProvider client={client}>
        <></>
      </OfflineProvider>,
    );
    mockSync.mockClear();
    (globalThis.fetch as jest.Mock).mockClear();

    await act(async () => {
      await jest.advanceTimersByTimeAsync(RECONNECT_INTERVAL_MS * 2 + 10);
    });
    expect((globalThis.fetch as jest.Mock).mock.calls.length).toBe(2);
    expect(getBackendStatus()).toBe('offline');
    expect(mockSync).not.toHaveBeenCalled();
  });
});
