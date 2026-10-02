import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

const mockPush = jest.fn();
jest.mock('expo-router', () => ({ useRouter: () => ({ push: mockPush }) }));

// eslint-disable-next-line @typescript-eslint/no-require-imports
const TodayScreen = require('../app/(tabs)/index').default;

const json = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

type Item = Record<string, unknown>;
const item = (id: string, overrides: Item = {}): Item => ({
  id,
  category: 'bottom',
  subcategory: null,
  colors: [{ name: 'negro', hex: '#222222', lab: [10, 0, 0], proportion: 1 }],
  status: 'active',
  needs_review: false,
  wear_count: 0,
  last_worn_at: null,
  created_at: '2026-01-01T10:00:00Z',
  img_thumb: null,
  job: null,
  ...overrides,
});

/** Answers the laundry request (status=laundry) and the usage request (status=active). */
function mockApi(
  laundry: { items: Item[]; total: number },
  active: { items: Item[]; total: number },
) {
  (globalThis.fetch as jest.Mock).mockImplementation(async (request: Request) => {
    const params = new URL(request.url).searchParams;
    const source = params.get('status') === 'laundry' ? laundry : active;
    return json({ ...source, page: 1, page_size: 50 });
  });
}

async function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <SafeAreaProvider
      initialMetrics={{
        frame: { x: 0, y: 0, width: 390, height: 844 },
        insets: { top: 0, left: 0, right: 0, bottom: 0 },
      }}
    >
      <QueryClientProvider client={client}>
        <TodayScreen />
      </QueryClientProvider>
    </SafeAreaProvider>,
  );
}

describe('TodayScreen (Hoy)', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = jest.fn();
    mockPush.mockClear();
  });
  afterEach(async () => {
    await cleanup();
    globalThis.fetch = originalFetch;
  });

  it('renders the empty-state copy from UI-REQ-005 and sends the user to Añadir', async () => {
    mockApi({ items: [], total: 0 }, { items: [], total: 0 });
    await renderScreen();

    expect(
      await screen.findByText('Aún no tienes suficientes prendas para generar un outfit'),
    ).toBeTruthy();
    await fireEvent.press(screen.getByRole('button', { name: 'Añadir prendas' }));
    expect(mockPush).toHaveBeenCalledWith('/(tabs)/add');
  });

  it('says proposals are coming soon, with the count, when there are garments', async () => {
    mockApi({ items: [], total: 2 }, { items: [item('a')], total: 3 });
    await renderScreen();

    expect(await screen.findByText('Tus propuestas diarias llegan pronto')).toBeTruthy();
    expect(
      screen.getByText(
        'Ya tienes 5 prendas en tu armario. Cuando activemos las sugerencias, aquí verás tu look de cada día.',
      ),
    ).toBeTruthy();
    expect(
      screen.queryByText('Aún no tienes suficientes prendas para generar un outfit'),
    ).toBeNull();
    expect(screen.queryByRole('button', { name: 'Añadir prendas' })).toBeNull();
    await fireEvent.press(screen.getByRole('button', { name: 'Ver tu armario' }));
    expect(mockPush).toHaveBeenCalledWith('/(tabs)/wardrobe');
  });

  it('uses the singular for a single garment', async () => {
    mockApi({ items: [], total: 0 }, { items: [item('a')], total: 1 });
    await renderScreen();

    expect(
      await screen.findByText(
        'Ya tienes 1 prenda en tu armario. Cuando activemos las sugerencias, aquí verás tu look de cada día.',
      ),
    ).toBeTruthy();
  });

  it('does not claim an empty wardrobe when the count fails', async () => {
    (globalThis.fetch as jest.Mock).mockRejectedValue(new Error('offline'));
    await renderScreen();

    expect(await screen.findByText('Tus propuestas diarias llegan pronto')).toBeTruthy();
    expect(screen.queryByText(/Ya tienes/)).toBeNull();
    expect(
      screen.queryByText('Aún no tienes suficientes prendas para generar un outfit'),
    ).toBeNull();
    expect(screen.queryByRole('button', { name: 'Añadir prendas' })).toBeNull();
  });

  it('shows neither state while the count loads', async () => {
    (globalThis.fetch as jest.Mock).mockReturnValue(new Promise(() => {}));
    await renderScreen();

    expect(screen.getByTestId('empty-state-loading')).toBeTruthy();
    expect(
      screen.queryByText('Aún no tienes suficientes prendas para generar un outfit'),
    ).toBeNull();
    expect(screen.queryByText('Tus propuestas diarias llegan pronto')).toBeNull();
  });

  it('shows a dated greeting and no weather, look or engine-only controls', async () => {
    mockApi({ items: [], total: 0 }, { items: [], total: 0 });
    await renderScreen();

    expect(
      screen.getByRole('header', { name: /^Buen(os días|as tardes|as noches)\./ }),
    ).toBeTruthy();
    expect(screen.queryByTestId('weather-pill')).toBeNull();
    expect(screen.queryByText('Look del día')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Me lo pongo' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Otra sugerencia' })).toBeNull();
  });

  it('lists the garments in the laundry basket and opens Armario', async () => {
    mockApi(
      { items: [item('1', { subcategory: 'vaquero' }), item('2', { category: 'top' })], total: 3 },
      { items: [], total: 0 },
    );
    await renderScreen();

    expect(await screen.findByText('3 prendas en el cesto')).toBeTruthy();
    expect(screen.getByText('Vaquero negro, top negro y 1 más.')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('tip-laundry'));
    expect(mockPush).toHaveBeenCalledWith('/(tabs)/wardrobe');
  });

  it('shows the share of the wardrobe worn and opens Historial', async () => {
    mockApi(
      { items: [], total: 0 },
      {
        items: [item('a', { wear_count: 4 }), item('b', { wear_count: 1 }), item('c'), item('d')],
        total: 4,
      },
    );
    await renderScreen();

    expect(await screen.findByText('Has usado el 50% de tu armario')).toBeTruthy();
    expect(screen.getByText('2 de 4 prendas activas se han puesto alguna vez.')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('tip-usage'));
    expect(mockPush).toHaveBeenCalledWith('/(tabs)/history');
  });

  it('hides the usage notice while nothing has been worn', async () => {
    mockApi({ items: [], total: 0 }, { items: [item('a'), item('b')], total: 2 });
    await renderScreen();
    await screen.findByText('Tus propuestas diarias llegan pronto');

    expect(screen.queryByTestId('tip-usage')).toBeNull();
  });

  it('omits both notices when the wardrobe has nothing to say', async () => {
    mockApi({ items: [], total: 0 }, { items: [], total: 0 });
    await renderScreen();
    await screen.findByText('Aún no tienes suficientes prendas para generar un outfit');

    expect(screen.queryByTestId('tip-laundry')).toBeNull();
    expect(screen.queryByTestId('tip-usage')).toBeNull();
  });
});
