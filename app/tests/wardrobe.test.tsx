import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

const mockPush = jest.fn();
jest.mock('expo-router', () => ({ useRouter: () => ({ push: mockPush }) }));

// eslint-disable-next-line @typescript-eslint/no-require-imports
const WardrobeScreen = require('../app/(tabs)/wardrobe').default;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

type Item = Record<string, unknown>;

const item = (id: string, overrides: Item = {}): Item => ({
  id,
  category: 'top',
  subcategory: null,
  colors: null,
  is_neutral: null,
  pattern: null,
  status: 'active',
  needs_review: false,
  user_verified: false,
  img_thumb: `thumb/${id}.webp`,
  img_cutout: `cutout/${id}.png`,
  wear_count: 0,
  last_worn_at: null,
  created_at: '2026-01-01T10:00:00Z',
  job: null,
  ...overrides,
});

const page = (items: Item[], total = items.length, pageNumber = 1) =>
  json({ items, total, page: pageNumber, page_size: 50 });

const fetchMock = () => globalThis.fetch as jest.Mock;
const LIST_PAGE_SIZE = '50';

type Handler = (request: Request) => Response | Promise<Response>;
type Counter = (params: URLSearchParams) => number;

/**
 * Routes the list request (page size 50) through `list` handlers, one per call, the last one
 * repeating; every counter request (page size 1) answers `counter(params)` as its total.
 */
function mockWardrobe(list: Handler[], counter: Counter = () => 0) {
  let calls = 0;
  fetchMock().mockImplementation(async (request: Request) => {
    const params = new URL(request.url).searchParams;
    if (params.get('page_size') !== LIST_PAGE_SIZE) {
      const total = counter(params);
      return page(total > 0 ? [item('counted')] : [], total);
    }
    return list[Math.min(calls++, list.length - 1)](request);
  });
}
/** A wardrobe that always lists `items`. */
const mockItems = (items: Item[], counter?: Counter) => mockWardrobe([() => page(items)], counter);

const listCalls = () =>
  (fetchMock().mock.calls as [Request][]).filter(
    ([request]) => new URL(request.url).searchParams.get('page_size') === LIST_PAGE_SIZE,
  );
const lastUrl = () => new URL(listCalls().at(-1)![0].url);
const counterUrls = () =>
  (fetchMock().mock.calls as [Request][])
    .map(([request]) => new URL(request.url))
    .filter((url) => url.searchParams.get('page_size') === '1');

async function renderScreen() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <SafeAreaProvider
      initialMetrics={{
        frame: { x: 0, y: 0, width: 390, height: 844 },
        insets: { top: 0, left: 0, right: 0, bottom: 0 },
      }}
    >
      <QueryClientProvider client={client}>
        <WardrobeScreen />
      </QueryClientProvider>
    </SafeAreaProvider>,
  );
}

describe('WardrobeScreen (Armario)', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = jest.fn();
    mockPush.mockClear();
  });

  afterEach(async () => {
    await cleanup();
    globalThis.fetch = originalFetch;
  });

  it('shows the grid skeleton while loading, then the garments', async () => {
    // Gate the list response so the skeleton is observable before it settles; an
    // already-resolved fetch can land inside render's act on a cold run.
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    mockWardrobe([
      async () => {
        await gate;
        return page([item('a'), item('b', { category: 'shoes' })]);
      },
    ]);
    await renderScreen();

    expect(screen.getByTestId('loading-state-grid')).toBeTruthy();
    await act(async () => release());
    expect(await screen.findByTestId('garment-card-a')).toBeTruthy();
    expect(screen.getByTestId('garment-card-b')).toBeTruthy();
    expect(within(screen.getByTestId('garment-card-b')).getByText('Calzado')).toBeTruthy();
    expect(screen.queryByTestId('loading-state-grid')).toBeNull();
  });

  it('requests active+laundry, newest first, page size 50 by default', async () => {
    mockItems([item('a')]);
    await renderScreen();
    await screen.findByTestId('garment-card-a');

    const url = lastUrl();
    expect(url.pathname).toBe('/garments');
    expect(url.searchParams.getAll('status')).toEqual(['active', 'laundry']);
    expect(url.searchParams.get('sort')).toBe('created_at');
    expect(url.searchParams.get('order')).toBe('desc');
    expect(url.searchParams.get('page_size')).toBe('50');
    expect(url.searchParams.get('page')).toBe('1');
  });

  it('shows the eyebrow with the wardrobe and active totals, and the title', async () => {
    mockItems([item('a')], (params) => (params.getAll('status').join() === 'active' ? 11 : 14));
    await renderScreen();

    expect(await screen.findByText('14 prendas · 11 activas')).toBeTruthy();
    expect(screen.getByText('Tu armario')).toBeTruthy();
  });

  it('counts each category and status with page-size-1 requests, scoped to the filters', async () => {
    mockItems([item('a')], (params) => {
      if (params.get('category') === 'shoes') return 3;
      if (params.getAll('status').join() === 'archived') return 2;
      return 9;
    });
    await renderScreen();
    await screen.findByTestId('garment-card-a');

    expect(await screen.findByLabelText('Calzado, 3')).toBeTruthy();
    expect(screen.getByLabelText('Archivadas, 2')).toBeTruthy();
    expect(screen.getByRole('tab', { name: 'Todas, 9' })).toBeTruthy();

    // The category counters follow the default status scope.
    const shoes = counterUrls().find((url) => url.searchParams.get('category') === 'shoes');
    expect(shoes?.searchParams.getAll('status')).toEqual(['active', 'laundry']);

    await fireEvent.press(screen.getByRole('tab', { name: /^Archivadas/ }));
    await waitFor(() => {
      const scoped = counterUrls().filter(
        (url) =>
          url.searchParams.get('category') === 'shoes' &&
          url.searchParams.getAll('status').join() === 'archived',
      );
      expect(scoped.length).toBeGreaterThan(0);
    });
  });

  it('shows the "Revisar" pill only on garments that need review (UI-REQ-004)', async () => {
    mockItems([item('a', { needs_review: true }), item('b')]);
    await renderScreen();
    await screen.findByTestId('garment-card-a');

    expect(screen.getAllByTestId('review-badge')).toHaveLength(1);
    expect(within(screen.getByTestId('garment-card-a')).getByText('Revisar')).toBeTruthy();
  });

  it('shows state pills: Lavando, Archivada and (only when unworn and recent) Nueva', async () => {
    const recent = new Date(Date.now() - 24 * 3600 * 1000).toISOString();
    mockItems([
      item('l', { status: 'laundry' }),
      item('x', { status: 'archived' }),
      item('n', { created_at: recent }),
      item('w', { created_at: recent, wear_count: 2 }),
      item('o'),
    ]);
    await renderScreen();
    await screen.findByTestId('garment-card-l');

    expect(within(screen.getByTestId('garment-card-l')).getByText('Lavando')).toBeTruthy();
    expect(within(screen.getByTestId('garment-card-x')).getByText('Archivada')).toBeTruthy();
    expect(within(screen.getByTestId('garment-card-n')).getByText('Nueva')).toBeTruthy();
    expect(within(screen.getByTestId('garment-card-w')).queryByText('Nueva')).toBeNull();
    expect(within(screen.getByTestId('garment-card-o')).queryByText('Nueva')).toBeNull();
  });

  it('names each garment and shows how often it was worn', async () => {
    mockItems([
      item('a', {
        subcategory: 'camiseta',
        colors: [{ name: 'negro', hex: '#191919', lab: [10, 0, 0], proportion: 1 }],
        wear_count: 3,
      }),
      item('b', { wear_count: 1 }),
      item('c'),
    ]);
    await renderScreen();
    await screen.findByTestId('garment-card-a');

    const a = within(screen.getByTestId('garment-card-a'));
    expect(a.getByText('Camiseta negra')).toBeTruthy();
    expect(a.getByText('Puesta 3 veces')).toBeTruthy();
    expect(within(screen.getByTestId('garment-card-b')).getByText('Puesta 1 vez')).toBeTruthy();
    expect(within(screen.getByTestId('garment-card-c')).getByText('Sin estrenar')).toBeTruthy();
  });

  it('shows a processing placeholder with progress when there is no thumbnail', async () => {
    mockItems([
      item('p', {
        img_thumb: null,
        category: null,
        job: { id: 'j', status: 'running', step: 'cutout', progress: 30, error: null },
      }),
    ]);
    await renderScreen();

    expect(await screen.findByTestId('garment-processing')).toBeTruthy();
    expect(screen.getByText('Procesando…')).toBeTruthy();
    expect(screen.getByText('Recortando')).toBeTruthy();
    expect(screen.getByRole('progressbar').props.accessibilityValue.now).toBe(30);
    expect(screen.queryByTestId('garment-thumb')).toBeNull();
  });

  it('polls the list every 2 s while a garment is processing', async () => {
    jest.useFakeTimers({ doNotFake: ['nextTick', 'queueMicrotask'] });
    try {
      const processing = item('p', {
        img_thumb: null,
        job: { id: 'j', status: 'pending', step: null, progress: 0, error: null },
      });
      mockWardrobe([() => page([processing]), () => page([item('p')])]);
      await renderScreen();
      await screen.findByTestId('garment-processing');
      expect(listCalls()).toHaveLength(1);

      await act(async () => {
        await jest.advanceTimersByTimeAsync(2100);
      });

      await waitFor(() => expect(screen.getByTestId('garment-thumb')).toBeTruthy());
      const calls = listCalls().length;
      await act(async () => {
        await jest.advanceTimersByTimeAsync(6000);
      });
      expect(listCalls().length).toBe(calls); // stops once nothing is processing
    } finally {
      jest.useRealTimers();
    }
  });

  it('shows the empty-wardrobe copy when there are no garments and no filters', async () => {
    mockItems([]);
    await renderScreen();

    expect(await screen.findByText('Tu armario está vacío')).toBeTruthy();
    await fireEvent.press(screen.getByLabelText('Añadir prenda'));
    expect(mockPush).toHaveBeenCalledWith('/(tabs)/add');
  });

  it('closes the grid with a dashed "Añadir prenda" tile that opens Añadir', async () => {
    mockItems([item('a')]);
    await renderScreen();
    await screen.findByTestId('garment-card-a');

    await fireEvent.press(screen.getByTestId('add-garment-tile'));
    expect(mockPush).toHaveBeenCalledWith('/(tabs)/add');
  });

  it('hides the "Añadir prenda" tile under Archivadas', async () => {
    mockItems([item('a', { status: 'archived' })]);
    await renderScreen();
    await screen.findByTestId('garment-card-a');
    expect(screen.getByTestId('add-garment-tile')).toBeTruthy();

    await fireEvent.press(screen.getByRole('tab', { name: /^Archivadas/ }));
    // The tile is also absent while the Archivadas query shows its skeleton, so the card and the
    // missing tile must hold together, not one after the other.
    await waitFor(() => {
      expect(screen.queryByTestId('add-garment-tile')).toBeNull();
      expect(screen.getByTestId('garment-card-a')).toBeTruthy();
    });
  });

  it('distinguishes "nothing here with these filters" and clears them', async () => {
    mockWardrobe([
      (request) =>
        new URL(request.url).searchParams.get('category') === 'shoes'
          ? page([])
          : page([item('a')]),
    ]);
    await renderScreen();
    await screen.findByTestId('garment-card-a');

    await fireEvent.press(screen.getByRole('button', { name: /^Calzado/ }));

    expect(await screen.findByText('Nada por aquí')).toBeTruthy();
    expect(screen.queryByText('Tu armario está vacío')).toBeNull();

    await fireEvent.press(screen.getByLabelText('Quitar filtros'));
    expect(await screen.findByTestId('garment-card-a')).toBeTruthy();
    expect(lastUrl().searchParams.has('category')).toBe(false);
  });

  it('shows an error state and retry refetches (UI-REQ-008)', async () => {
    mockWardrobe([
      () => json({ error: { code: 'X', message: 'Servidor caído.' } }, 500),
      () => page([item('a')]),
    ]);
    await renderScreen();

    expect(await screen.findByText('Servidor caído.')).toBeTruthy();
    await fireEvent.press(screen.getByLabelText('Reintentar'));

    expect(await screen.findByTestId('garment-card-a')).toBeTruthy();
    expect(screen.queryByTestId('error-state')).toBeNull();
    expect(listCalls()).toHaveLength(2);
  });

  it('changes the request when category chips and status segments are pressed', async () => {
    mockItems([item('a')]);
    await renderScreen();
    await screen.findByTestId('garment-card-a');

    await fireEvent.press(screen.getByRole('button', { name: /^Pantalón/ }));
    await waitFor(() => expect(lastUrl().searchParams.get('category')).toBe('bottom'));

    await fireEvent.press(screen.getByRole('tab', { name: /^Activas/ }));
    await waitFor(() => expect(lastUrl().searchParams.getAll('status')).toEqual(['active']));

    await fireEvent.press(screen.getByRole('tab', { name: /^Archivadas/ }));
    await waitFor(() => expect(lastUrl().searchParams.getAll('status')).toEqual(['archived']));

    await fireEvent.press(screen.getByRole('tab', { name: /^Todas/ }));
    await waitFor(() =>
      expect(lastUrl().searchParams.getAll('status')).toEqual(['active', 'laundry', 'archived']),
    );

    // Pressing the highlighted segment again goes back to the default view.
    await fireEvent.press(screen.getByRole('tab', { name: /^Todas/ }));
    await waitFor(() =>
      expect(lastUrl().searchParams.getAll('status')).toEqual(['active', 'laundry']),
    );

    await fireEvent.press(screen.getByRole('button', { name: /^Todas/ }));
    await waitFor(() => expect(lastUrl().searchParams.has('category')).toBe(false));
  });

  it('highlights no status segment in the default active+laundry view', async () => {
    mockItems([item('a')]);
    await renderScreen();
    await screen.findByTestId('garment-card-a');

    for (const tab of screen.getAllByRole('tab')) {
      expect(tab.props.accessibilityState.selected).toBe(false);
    }
  });

  describe('review banner', () => {
    const pending = (total: number) => (params: URLSearchParams) =>
      params.get('needs_review') === 'true' ? total : 9;

    it('is hidden when no garment is pending review', async () => {
      mockItems([item('a')], pending(0));
      await renderScreen();
      await screen.findByTestId('garment-card-a');

      expect(screen.queryByTestId('review-banner')).toBeNull();
    });

    it('shows the pending count and opens the garment when only one is pending', async () => {
      fetchMock().mockImplementation(async (request: Request) => {
        const params = new URL(request.url).searchParams;
        if (params.get('page_size') === LIST_PAGE_SIZE) return page([item('a')]);
        if (params.get('needs_review') === 'true') return page([item('solo')], 1);
        return page([item('counted')], 9);
      });
      await renderScreen();

      const banner = await screen.findByTestId('review-banner');
      expect(within(banner).getByText(/1 prenda pendiente de revisión/)).toBeTruthy();

      await fireEvent.press(within(banner).getByLabelText('Revisar'));
      expect(mockPush).toHaveBeenCalledWith('/review/solo');
    });

    it('lists the pending garments behind a removable chip when several are pending', async () => {
      mockWardrobe([() => page([item('a'), item('b', { needs_review: true })])], pending(3));
      await renderScreen();

      const banner = await screen.findByTestId('review-banner');
      expect(within(banner).getByText(/3 prendas pendientes de revisión/)).toBeTruthy();

      await fireEvent.press(within(banner).getByLabelText('Revisar'));
      await waitFor(() => expect(lastUrl().searchParams.get('needs_review')).toBe('true'));
      expect(mockPush).not.toHaveBeenCalled();
      expect(screen.queryByTestId('review-banner')).toBeNull();

      await fireEvent.press(await screen.findByTestId('review-filter'));
      await waitFor(() => expect(lastUrl().searchParams.has('needs_review')).toBe(false));
      expect(await screen.findByTestId('review-banner')).toBeTruthy();
    });
  });

  it('loads the next page with "Cargar más"', async () => {
    mockWardrobe([
      (request) =>
        new URL(request.url).searchParams.get('page') === '2'
          ? page([item('b')], 2, 2)
          : page([item('a')], 2, 1),
    ]);
    await renderScreen();
    await screen.findByTestId('garment-card-a');

    await fireEvent.press(screen.getByLabelText('Cargar más'));

    expect(await screen.findByTestId('garment-card-b')).toBeTruthy();
    expect(screen.getByTestId('garment-card-a')).toBeTruthy();
    expect(screen.queryByLabelText('Cargar más')).toBeNull();
  });

  it('drops repeated garment ids across pages, first occurrence wins (offset pagination)', async () => {
    mockWardrobe([
      (request) =>
        new URL(request.url).searchParams.get('page') === '2'
          ? page([item('a', { category: 'shoes' }), item('b')], 3, 2)
          : page([item('a')], 3, 1),
    ]);
    await renderScreen();
    await screen.findByTestId('garment-card-a');

    await fireEvent.press(screen.getByLabelText('Cargar más'));

    expect(await screen.findByTestId('garment-card-b')).toBeTruthy();
    expect(screen.getAllByTestId('garment-card-a')).toHaveLength(1);
  });

  it('keeps the grid and offers Reintentar when loading the next page fails', async () => {
    let failNext = true;
    mockWardrobe([
      (request) => {
        if (new URL(request.url).searchParams.get('page') !== '2') return page([item('a')], 2, 1);
        return failNext
          ? json({ error: { code: 'X', message: 'Sin conexión con el servidor.' } }, 500)
          : page([item('b')], 2, 2);
      },
    ]);
    await renderScreen();
    await screen.findByTestId('garment-card-a');

    await fireEvent.press(screen.getByLabelText('Cargar más'));

    const banner = await screen.findByTestId('wardrobe-soft-error');
    expect(within(banner).getByText('Sin conexión con el servidor.')).toBeTruthy();
    expect(screen.getByTestId('garment-card-a')).toBeTruthy();
    expect(screen.queryByTestId('error-state')).toBeNull();

    failNext = false;
    await fireEvent.press(within(banner).getByLabelText('Reintentar'));

    expect(await screen.findByTestId('garment-card-b')).toBeTruthy();
    await waitFor(() => expect(screen.queryByTestId('wardrobe-soft-error')).toBeNull());
    expect(screen.getByTestId('garment-card-a')).toBeTruthy();
  });

  it('keeps the grid and shows the error when a background poll fails, then recovers', async () => {
    jest.useFakeTimers({ doNotFake: ['nextTick', 'queueMicrotask'] });
    try {
      const processing = item('p', {
        img_thumb: null,
        job: { id: 'j', status: 'running', step: 'cutout', progress: 30, error: null },
      });
      mockWardrobe([
        () => page([processing]),
        () => json({ error: { code: 'X', message: 'Servidor caído.' } }, 500),
        () => page([item('p')]),
      ]);
      await renderScreen();
      await screen.findByTestId('garment-processing');

      await act(async () => {
        await jest.advanceTimersByTimeAsync(2100);
      });

      expect(await screen.findByTestId('wardrobe-soft-error')).toBeTruthy();
      expect(screen.getByText('Servidor caído.')).toBeTruthy();
      expect(screen.getByTestId('garment-processing')).toBeTruthy();

      await fireEvent.press(screen.getByLabelText('Reintentar'));

      expect(await screen.findByTestId('garment-thumb')).toBeTruthy();
      await waitFor(() => expect(screen.queryByTestId('wardrobe-soft-error')).toBeNull());
    } finally {
      jest.useRealTimers();
    }
  });

  it('keeps the grid and shows the error when a pull-to-refresh fails', async () => {
    mockWardrobe([
      () => page([item('a')]),
      () => json({ error: { code: 'X', message: 'No se pudo refrescar.' } }, 500),
    ]);
    await renderScreen();
    await screen.findByTestId('garment-card-a');

    const { refreshControl } = screen.getByTestId('wardrobe-list').props;
    await act(async () => {
      refreshControl.props.onRefresh();
    });

    expect(await screen.findByText('No se pudo refrescar.')).toBeTruthy();
    expect(screen.getByTestId('garment-card-a')).toBeTruthy();
  });

  it('refreshes the counters and the review banner on pull-to-refresh', async () => {
    let pending = 1;
    mockItems([item('a')], (params) => (params.get('needs_review') === 'true' ? pending : 5));
    await renderScreen();
    await screen.findByTestId('review-banner');
    const before = counterUrls().length;

    pending = 0;
    const { refreshControl } = screen.getByTestId('wardrobe-list').props;
    await act(async () => {
      refreshControl.props.onRefresh();
    });

    await waitFor(() => expect(screen.queryByTestId('review-banner')).toBeNull());
    expect(counterUrls().length).toBeGreaterThan(before);
    expect(screen.getByTestId('wardrobe-list').props.refreshControl.props.refreshing).toBe(false);
  });

  it('opens the garment detail when a card is tapped', async () => {
    mockItems([item('abc')]);
    await renderScreen();

    await fireEvent.press(await screen.findByTestId('garment-card-abc'));

    expect(mockPush).toHaveBeenCalledWith('/garments/abc');
  });
});
