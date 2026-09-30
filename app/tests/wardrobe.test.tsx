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
  created_at: '2026-09-30T10:00:00Z',
  job: null,
  ...overrides,
});

const page = (items: Item[], total = items.length, pageNumber = 1) =>
  json({ items, total, page: pageNumber, page_size: 50 });

const fetchMock = () => globalThis.fetch as jest.Mock;
const lastUrl = () => new URL((fetchMock().mock.calls.at(-1)?.[0] as Request).url);

async function renderScreen() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <WardrobeScreen />
    </QueryClientProvider>,
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
    fetchMock().mockResolvedValue(page([item('a'), item('b', { category: 'shoes' })]));
    await renderScreen();

    expect(screen.getByTestId('loading-state-grid')).toBeTruthy();
    expect(await screen.findByTestId('garment-card-a')).toBeTruthy();
    expect(screen.getByTestId('garment-card-b')).toBeTruthy();
    expect(within(screen.getByTestId('garment-card-b')).getByText('Calzado')).toBeTruthy();
    expect(screen.queryByTestId('loading-state-grid')).toBeNull();
  });

  it('requests active+laundry, newest first, page size 50 by default', async () => {
    fetchMock().mockResolvedValue(page([item('a')]));
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

  it('shows the "Revisar" badge only on garments that need review (UI-REQ-004)', async () => {
    fetchMock().mockResolvedValue(page([item('a', { needs_review: true }), item('b')]));
    await renderScreen();
    await screen.findByTestId('garment-card-a');

    expect(screen.getAllByTestId('review-badge')).toHaveLength(1);
    expect(screen.getByText('Revisar')).toBeTruthy();
  });

  it('shows a processing placeholder with progress when there is no thumbnail', async () => {
    fetchMock().mockResolvedValue(
      page([
        item('p', {
          img_thumb: null,
          category: null,
          job: { id: 'j', status: 'running', step: 'cutout', progress: 30, error: null },
        }),
      ]),
    );
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
      fetchMock()
        .mockResolvedValueOnce(page([processing]))
        .mockResolvedValue(page([item('p')]));
      await renderScreen();
      await screen.findByTestId('garment-processing');
      expect(fetchMock()).toHaveBeenCalledTimes(1);

      await act(async () => {
        await jest.advanceTimersByTimeAsync(2100);
      });

      await waitFor(() => expect(screen.getByTestId('garment-thumb')).toBeTruthy());
      const calls = fetchMock().mock.calls.length;
      await act(async () => {
        await jest.advanceTimersByTimeAsync(6000);
      });
      expect(fetchMock().mock.calls.length).toBe(calls); // stops once nothing is processing
    } finally {
      jest.useRealTimers();
    }
  });

  it('shows the empty-wardrobe copy when there are no garments and no filters', async () => {
    fetchMock().mockResolvedValue(page([]));
    await renderScreen();

    expect(await screen.findByText('Tu armario está vacío')).toBeTruthy();
    await fireEvent.press(screen.getByLabelText('Añadir prenda'));
    expect(mockPush).toHaveBeenCalledWith('/(tabs)/add');
  });

  it('distinguishes "no results with these filters" and clears them', async () => {
    fetchMock().mockImplementation(async (request: Request) =>
      new URL(request.url).searchParams.get('category') === 'shoes' ? page([]) : page([item('a')]),
    );
    await renderScreen();
    await screen.findByTestId('garment-card-a');

    await fireEvent.press(screen.getByLabelText('Categoría: Calzado'));

    expect(await screen.findByText('Ninguna prenda coincide con estos filtros')).toBeTruthy();
    expect(screen.queryByText('Tu armario está vacío')).toBeNull();

    await fireEvent.press(screen.getByLabelText('Quitar filtros'));
    expect(await screen.findByTestId('garment-card-a')).toBeTruthy();
    expect(lastUrl().searchParams.has('category')).toBe(false);
  });

  it('shows an error state and retry refetches (UI-REQ-008)', async () => {
    fetchMock()
      .mockResolvedValueOnce(json({ error: { code: 'X', message: 'Servidor caído.' } }, 500))
      .mockResolvedValue(page([item('a')]));
    await renderScreen();

    expect(await screen.findByText('Servidor caído.')).toBeTruthy();
    await fireEvent.press(screen.getByLabelText('Reintentar'));

    expect(await screen.findByTestId('garment-card-a')).toBeTruthy();
    expect(screen.queryByTestId('error-state')).toBeNull();
    expect(fetchMock()).toHaveBeenCalledTimes(2);
  });

  it('changes the request when filter chips are pressed', async () => {
    fetchMock().mockResolvedValue(page([item('a')]));
    await renderScreen();
    await screen.findByTestId('garment-card-a');

    await fireEvent.press(screen.getByLabelText('Categoría: Pantalón'));
    await waitFor(() => expect(lastUrl().searchParams.get('category')).toBe('bottom'));

    await fireEvent.press(screen.getByLabelText('Estado: Archivadas'));
    await waitFor(() => expect(lastUrl().searchParams.getAll('status')).toEqual(['archived']));

    await fireEvent.press(screen.getByLabelText('Estado: Todas'));
    await waitFor(() =>
      expect(lastUrl().searchParams.getAll('status')).toEqual(['active', 'laundry', 'archived']),
    );

    await fireEvent.press(screen.getByLabelText('Filtro: Pendientes de revisión'));
    await waitFor(() => expect(lastUrl().searchParams.get('needs_review')).toBe('true'));

    await fireEvent.press(screen.getByLabelText('Categoría: Todas'));
    await waitFor(() => expect(lastUrl().searchParams.has('category')).toBe(false));
  });

  it('loads the next page with "Cargar más"', async () => {
    fetchMock().mockImplementation(async (request: Request) =>
      new URL(request.url).searchParams.get('page') === '2'
        ? page([item('b')], 2, 2)
        : page([item('a')], 2, 1),
    );
    await renderScreen();
    await screen.findByTestId('garment-card-a');

    await fireEvent.press(screen.getByLabelText('Cargar más'));

    expect(await screen.findByTestId('garment-card-b')).toBeTruthy();
    expect(screen.getByTestId('garment-card-a')).toBeTruthy();
    expect(screen.queryByLabelText('Cargar más')).toBeNull();
  });

  it('drops repeated garment ids across pages, first occurrence wins (offset pagination)', async () => {
    fetchMock().mockImplementation(async (request: Request) =>
      new URL(request.url).searchParams.get('page') === '2'
        ? page([item('a', { category: 'shoes' }), item('b')], 3, 2)
        : page([item('a')], 3, 1),
    );
    await renderScreen();
    await screen.findByTestId('garment-card-a');

    await fireEvent.press(screen.getByLabelText('Cargar más'));

    expect(await screen.findByTestId('garment-card-b')).toBeTruthy();
    expect(screen.getAllByTestId('garment-card-a')).toHaveLength(1);
  });

  it('keeps the grid and offers Reintentar when loading the next page fails', async () => {
    let failNext = true;
    fetchMock().mockImplementation(async (request: Request) => {
      if (new URL(request.url).searchParams.get('page') !== '2') return page([item('a')], 2, 1);
      return failNext
        ? json({ error: { code: 'X', message: 'Sin conexión con el servidor.' } }, 500)
        : page([item('b')], 2, 2);
    });
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
      fetchMock()
        .mockResolvedValueOnce(page([processing]))
        .mockResolvedValueOnce(json({ error: { code: 'X', message: 'Servidor caído.' } }, 500))
        .mockResolvedValue(page([item('p')]));
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
    fetchMock()
      .mockResolvedValueOnce(page([item('a')]))
      .mockResolvedValue(json({ error: { code: 'X', message: 'No se pudo refrescar.' } }, 500));
    await renderScreen();
    await screen.findByTestId('garment-card-a');

    const { refreshControl } = screen.getByTestId('wardrobe-list').props;
    await act(async () => {
      refreshControl.props.onRefresh();
    });

    expect(await screen.findByText('No se pudo refrescar.')).toBeTruthy();
    expect(screen.getByTestId('garment-card-a')).toBeTruthy();
  });

  it('opens the garment detail when a card is tapped', async () => {
    fetchMock().mockResolvedValue(page([item('abc')]));
    await renderScreen();

    await fireEvent.press(await screen.findByTestId('garment-card-abc'));

    expect(mockPush).toHaveBeenCalledWith('/garments/abc');
  });
});
