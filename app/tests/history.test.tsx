import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

const mockPush = jest.fn();
jest.mock('expo-router', () => ({ useRouter: () => ({ push: mockPush }) }));

// eslint-disable-next-line @typescript-eslint/no-require-imports
const HistoryScreen = require('../app/(tabs)/history').default;

const json = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

type Item = Record<string, unknown>;
const DAY = 24 * 60 * 60 * 1000;
const item = (id: string, overrides: Item = {}): Item => ({
  id,
  category: 'top',
  subcategory: null,
  colors: [{ name: 'azul', hex: '#3355AA', lab: [10, 0, 0], proportion: 1 }],
  status: 'active',
  needs_review: false,
  wear_count: 0,
  last_worn_at: null,
  created_at: '2026-01-01T10:00:00Z',
  img_thumb: null,
  job: null,
  ...overrides,
});

/** Routes the three requests Historial makes by their sort parameters. */
function mockApi(pages: { usage: Item[]; unworn?: Item[]; stale?: Item[] }) {
  (globalThis.fetch as jest.Mock).mockImplementation(async (request: Request) => {
    const params = new URL(request.url).searchParams;
    let items = pages.usage;
    if (params.get('sort') === 'wear_count' && params.get('order') === 'asc') {
      items = pages.unworn ?? [];
    } else if (params.get('sort') === 'last_worn_at') {
      items = pages.stale ?? [];
    }
    const total = params.get('page_size') === '200' ? pages.usage.length : items.length;
    return json({ items, total, page: 1, page_size: 50 });
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
        <HistoryScreen />
      </QueryClientProvider>
    </SafeAreaProvider>,
  );
}

describe('HistoryScreen (Historial)', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = jest.fn();
    mockPush.mockClear();
  });
  afterEach(async () => {
    await cleanup();
    globalThis.fetch = originalFetch;
  });

  it('renders the exact empty-state copy from UI-REQ-007 and no calendar', async () => {
    mockApi({ usage: [] });
    await renderScreen();

    expect(screen.getByText('Todavía no has registrado ningún outfit')).toBeTruthy();
    expect(screen.queryByTestId('month-calendar')).toBeNull();
    expect(screen.getByRole('header', { name: 'Historial' })).toBeTruthy();
  });

  it('shows the usage KPIs only once the wardrobe can be measured', async () => {
    mockApi({
      usage: [item('a', { wear_count: 4 }), item('b', { wear_count: 1 }), item('c'), item('d')],
    });
    await renderScreen();

    expect(await screen.findByText('50%')).toBeTruthy();
    expect(screen.getByText('del armario usado')).toBeTruthy();
    expect(screen.getByText('prendas sin estrenar')).toBeTruthy();
    expect(screen.getByTestId('kpi-unworn')).toHaveTextContent('2prendas sin estrenar');
    // Nothing the API cannot compute is invented.
    expect(screen.queryByText(/looks este mes/)).toBeNull();
    expect(screen.queryByText(/coste/)).toBeNull();
  });

  it('lists the most worn with a bar relative to the first and opens Detalle', async () => {
    mockApi({
      usage: [
        item('a', { wear_count: 8, subcategory: 'camiseta' }),
        item('b', { wear_count: 2 }),
        item('c'),
      ],
    });
    await renderScreen();

    expect(await screen.findByText('Las que más usas')).toBeTruthy();
    expect(screen.getByText('8 usos')).toBeTruthy();
    expect(screen.getByText('2 usos')).toBeTruthy();
    expect(screen.getByLabelText('Uso de Camiseta azul').props.accessibilityValue.now).toBe(100);
    expect(screen.getByLabelText('Uso de Top azul').props.accessibilityValue.now).toBe(25);
    await fireEvent.press(screen.getByRole('button', { name: 'Abrir prenda Camiseta azul' }));
    expect(mockPush).toHaveBeenCalledWith('/garments/a');
  });

  it('hides the most-worn card while nothing has been worn', async () => {
    mockApi({ usage: [item('a'), item('b')], unworn: [item('a'), item('b')] });
    await renderScreen();
    await screen.findByTestId('kpi-unworn');

    expect(screen.queryByText('Las que más usas')).toBeNull();
    // Truthful at zero: no "0%" KPI, only the unworn count and an honest list title.
    expect(screen.queryByTestId('kpi-usage')).toBeNull();
    expect(screen.queryByText('0%')).toBeNull();
    expect(screen.getByTestId('kpi-unworn')).toHaveTextContent('2prendas sin estrenar');
    expect(screen.queryByText('Dales otra oportunidad')).toBeNull();
    expect(await screen.findByText('Aún sin estrenar')).toBeTruthy();
  });

  it('offers unworn garments, then ones worn long ago, with no suggest button', async () => {
    const old = new Date(Date.now() - 80 * DAY).toISOString();
    const recent = new Date(Date.now() - 3 * DAY).toISOString();
    mockApi({
      usage: [item('w', { wear_count: 3, last_worn_at: old }), item('n')],
      unworn: [item('n', { subcategory: 'camisa' })],
      stale: [
        item('w', { wear_count: 3, last_worn_at: old, subcategory: 'jersey' }),
        item('r', { wear_count: 1, last_worn_at: recent }),
        item('n', { subcategory: 'camisa' }),
      ],
    });
    await renderScreen();

    expect(await screen.findByText('Dales otra oportunidad')).toBeTruthy();
    expect(screen.getByText('Sin estrenar')).toBeTruthy();
    expect(screen.getByText('Hace 80 días')).toBeTruthy();
    expect(screen.queryByText(/Hace 3/)).toBeNull();
    expect(screen.queryByRole('button', { name: /Sugerir/ })).toBeNull();
    await fireEvent.press(screen.getByRole('button', { name: 'Abrir prenda Camisa azul' }));
    expect(mockPush).toHaveBeenCalledWith('/garments/n');
  });

  it('shows an error state instead of an empty wardrobe, and retry refetches', async () => {
    let failing = true;
    (globalThis.fetch as jest.Mock).mockImplementation(async () =>
      failing
        ? new Response(JSON.stringify({ error: { code: 'X', message: 'Servidor caído.' } }), {
            status: 500,
            headers: { 'Content-Type': 'application/json' },
          })
        : json({ items: [item('a', { wear_count: 3 })], total: 1, page: 1, page_size: 50 }),
    );
    await renderScreen();

    expect(await screen.findByText('Servidor caído.')).toBeTruthy();
    expect(screen.queryByTestId('empty-state')).toBeNull();

    failing = false;
    await fireEvent.press(screen.getByLabelText('Reintentar'));

    expect(await screen.findByTestId('kpi-usage')).toBeTruthy();
    expect(screen.queryByTestId('error-state')).toBeNull();
  });
});
