import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react-native';
import { Dimensions, StyleSheet } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { ToastProvider } from '@/components/ui';

const mockPush = jest.fn();
const mockReplace = jest.fn();
const mockBack = jest.fn();
let mockCanGoBack = true;
jest.mock('expo-router', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: mockReplace,
    back: mockBack,
    canGoBack: () => mockCanGoBack,
  }),
  useLocalSearchParams: () => ({ id: 'g1' }),
}));

// eslint-disable-next-line @typescript-eslint/no-require-imports
const DetailScreen = require('../app/garments/[id]').default;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

const baseGarment = (): Record<string, unknown> => ({
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
});

let garment: Record<string, unknown>;
let calls: { method: string; path: string; body: unknown }[];
let deleteResponse: () => Response;

async function handle(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const body =
    request.method === 'GET'
      ? null
      : await request
          .clone()
          .json()
          .catch(() => null);
  calls.push({ method: request.method, path: url.pathname, body });
  const key = `${request.method} ${url.pathname}`;
  switch (key) {
    case 'GET /garments/g1':
      return json(garment);
    case 'GET /jobs/j1':
      return json({ status: 'running', step: 'color', progress: 60, error: null, result: null });
    case 'PATCH /garments/g1':
      garment = { ...garment, ...(body as object) };
      return json(garment);
    case 'POST /garments/g1/archive':
      garment = { ...garment, status: 'archived' };
      return json(garment);
    case 'POST /garments/g1/reactivate':
      garment = { ...garment, status: 'active' };
      return json(garment);
    case 'POST /garments/g1/retry':
      garment = {
        ...garment,
        job: { id: 'j2', status: 'pending', step: null, progress: 0, error: null },
      };
      return json({ status: 'pending', step: null, progress: 0, error: null, result: null }, 202);
    case 'DELETE /garments/g1':
      return deleteResponse();
    default:
      return json({ error: { code: 'NOT_FOUND', message: 'no', details: null } }, 404);
  }
}

async function renderScreen() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { gcTime: 0 } },
  });
  const spy = jest.spyOn(client, 'invalidateQueries');
  const view = await render(
    <SafeAreaProvider
      initialMetrics={{
        frame: { x: 0, y: 0, width: 390, height: 844 },
        insets: { top: 0, left: 0, right: 0, bottom: 0 },
      }}
    >
      <ToastProvider>
        <QueryClientProvider client={client}>
          <DetailScreen />
        </QueryClientProvider>
      </ToastProvider>
    </SafeAreaProvider>,
  );
  return { view, spy };
}

const posts = (path: string) => calls.filter((c) => c.method === 'POST' && c.path === path);
const invalidatedKeys = (spy: jest.SpyInstance) =>
  spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey));

describe('GarmentDetailScreen (Detalle)', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    garment = baseGarment();
    calls = [];
    deleteResponse = () => new Response(null, { status: 204 });
    mockPush.mockClear();
    mockReplace.mockClear();
    mockBack.mockClear();
    mockCanGoBack = true;
    globalThis.fetch = jest.fn((input: Request) => handle(input)) as unknown as typeof fetch;
  });

  afterEach(async () => {
    await cleanup();
    globalThis.fetch = originalFetch;
  });

  it('renders the cutout, composed name, Spanish attributes and usage', async () => {
    await renderScreen();
    expect(await screen.findByTestId('detail-image')).toBeTruthy();
    expect(screen.getByText('Capa intermedia')).toBeTruthy(); // eyebrow
    expect(screen.getByText('Jersey marino de lana')).toBeTruthy(); // composed title
    expect(screen.getByText('Rayas')).toBeTruthy();
    expect(screen.getByLabelText('Otoño, activa')).toBeTruthy();
    expect(screen.getByLabelText('Invierno, activa')).toBeTruthy();
    expect(screen.getByLabelText('Primavera')).toBeTruthy();
    expect(screen.getByText('Clásico')).toBeTruthy();
    expect(screen.getByText('lana')).toBeTruthy();
    expect(screen.getByText('marino')).toBeTruthy();
    expect(screen.getByLabelText('Formalidad: Smart casual, 3 de 5')).toBeTruthy();
    expect(screen.getByText('4 de 5')).toBeTruthy();
    expect(screen.getByLabelText('veces puesta: 7')).toBeTruthy();
    expect(screen.getByLabelText('última vez: Nunca')).toBeTruthy();
    expect(screen.getByLabelText('outfits: 5')).toBeTruthy();
    expect(within(screen.getByTestId('detail-status')).getByText('En el armario')).toBeTruthy();
  });

  it('shows "+ Añadir" chips for empty attributes instead of "Sin definir"', async () => {
    await renderScreen();
    await screen.findByTestId('detail-image');
    // brand and notes are empty in the base garment
    await fireEvent.press(screen.getByLabelText('Añadir marca'));
    expect(mockPush).toHaveBeenLastCalledWith('/review/g1');
    await fireEvent.press(screen.getByLabelText('Añadir notas'));
    expect(screen.queryByText('Sin definir')).toBeNull();
    expect(screen.queryByLabelText('Añadir material')).toBeNull();
    await cleanup();

    garment = {
      ...baseGarment(),
      colors: null,
      style_tags: [],
      seasons: [],
      pattern: null,
      formality: null,
      warmth: null,
      material: null,
    };
    await renderScreen();
    await screen.findByTestId('detail-image');
    for (const what of [
      'colores',
      'estilo',
      'formalidad',
      'temporada',
      'estampado',
      'material',
      'abrigo',
    ]) {
      expect(screen.getByLabelText(`Añadir ${what}`)).toBeTruthy();
    }
    expect(screen.queryByText('Sin definir')).toBeNull();
  });

  it('opens Revisión from "Editar"', async () => {
    await renderScreen();
    await fireEvent.press(await screen.findByLabelText('Editar atributos'));
    expect(mockPush).toHaveBeenCalledWith('/review/g1');
  });

  it('does not offer "Crear outfit con esta prenda" (no outfit engine yet)', async () => {
    await renderScreen();
    await screen.findByTestId('detail-image');
    expect(screen.queryByText('Crear outfit con esta prenda')).toBeNull();
  });

  it('shows the analysed badge only when the garment has a cutout', async () => {
    await renderScreen();
    expect(await screen.findByText('Recortada y analizada automáticamente')).toBeTruthy();
    await cleanup();

    garment = { ...baseGarment(), img_cutout: null };
    await renderScreen();
    await screen.findByTestId('detail-image');
    expect(screen.queryByText('Recortada y analizada automáticamente')).toBeNull();
  });

  it('goes back, or to Armario when there is no history', async () => {
    await renderScreen();
    await screen.findByTestId('detail-image');
    const btn = screen.getByLabelText('Volver');
    await fireEvent.press(btn);
    expect(mockBack).toHaveBeenCalledTimes(1);
    await cleanup();

    mockCanGoBack = false;
    await renderScreen();
    await screen.findByTestId('detail-image');
    await fireEvent.press(screen.getByLabelText('Volver'));
    expect(mockReplace).toHaveBeenCalledWith('/(tabs)/wardrobe');
  });

  it('keeps a way back on the not-found state', async () => {
    globalThis.fetch = jest.fn(() =>
      Promise.resolve(
        json({ error: { code: 'GARMENT_NOT_FOUND', message: 'x', details: null } }, 404),
      ),
    ) as unknown as typeof fetch;
    await renderScreen();
    await screen.findByText('No encontramos esta prenda');
    await fireEvent.press(screen.getByLabelText('Volver'));
    expect(mockBack).toHaveBeenCalled();
  });

  it('lays out two columns from 880 px and one below', async () => {
    const window = (width: number) => ({ width, height: 900, scale: 2, fontScale: 1 });
    const spy = jest.spyOn(Dimensions, 'get');
    const layout = () => StyleSheet.flatten(screen.getByTestId('detail-page').props.style);
    try {
      spy.mockReturnValue(window(1200));
      await renderScreen();
      await screen.findByTestId('detail-image');
      expect(layout().flexDirection).toBe('row');
      await cleanup();

      spy.mockReturnValue(window(390));
      await renderScreen();
      await screen.findByTestId('detail-image');
      expect(layout().flexDirection).toBeUndefined();
    } finally {
      spy.mockRestore();
    }
  });

  it('marks as laundry via PATCH and invalidates list and detail', async () => {
    const { spy } = await renderScreen();
    await fireEvent.press(await screen.findByLabelText('Marcar como lavando'));
    await waitFor(() =>
      expect(calls.filter((c) => c.method === 'PATCH').map((c) => c.body)).toEqual([
        { status: 'laundry' },
      ]),
    );
    await waitFor(() =>
      expect(within(screen.getByTestId('detail-status')).getByText('Lavando')).toBeTruthy(),
    );
    expect(await screen.findByText('Marcada como lavando')).toBeTruthy(); // toast
    expect(invalidatedKeys(spy)).toEqual(
      expect.arrayContaining([
        JSON.stringify(['garments', 'list']),
        JSON.stringify(['garments', 'detail', 'g1']),
      ]),
    );
    expect(screen.getByLabelText('Marcar como activa')).toBeTruthy();
  });

  it('archives and reactivates', async () => {
    const { spy } = await renderScreen();
    await fireEvent.press(await screen.findByLabelText('Archivar'));
    await waitFor(() => expect(posts('/garments/g1/archive')).toHaveLength(1));
    expect(await screen.findByText('Prenda archivada')).toBeTruthy(); // toast
    expect(screen.queryByLabelText('Marcar como lavando')).toBeNull();
    await fireEvent.press(await screen.findByLabelText('Reactivar'));
    await waitFor(() => expect(posts('/garments/g1/reactivate')).toHaveLength(1));
    expect(invalidatedKeys(spy)).toContain(JSON.stringify(['garments', 'detail', 'g1']));
  });

  it('links to Revisión and shows the review badge when pending', async () => {
    garment = { ...baseGarment(), needs_review: true };
    await renderScreen();
    expect(await screen.findByTestId('review-badge')).toBeTruthy();
    expect(screen.getByText('Pendiente de revisión')).toBeTruthy();
    await fireEvent.press(screen.getByLabelText('Revisar'));
    expect(mockPush).toHaveBeenCalledWith('/review/g1');
  });

  it('offers "Reintentar procesamiento" only when the latest job failed', async () => {
    await renderScreen();
    await screen.findByTestId('detail-image');
    expect(screen.queryByLabelText('Reintentar procesamiento')).toBeNull();
    await cleanup();

    garment = {
      ...baseGarment(),
      job: {
        id: 'j1',
        status: 'failed',
        step: 'cutout',
        progress: 30,
        error: 'No se pudo recortar',
      },
    };
    await renderScreen();
    expect(await screen.findByText('No se pudo recortar')).toBeTruthy();
    await fireEvent.press(screen.getByLabelText('Reintentar procesamiento'));
    await waitFor(() => expect(posts('/garments/g1/retry')).toHaveLength(1));
  });

  it('shows job progress while the garment is processing', async () => {
    garment = {
      ...baseGarment(),
      job: { id: 'j1', status: 'running', step: 'color', progress: 10, error: null },
    };
    await renderScreen();
    expect(await screen.findByTestId('detail-processing')).toBeTruthy();
    await waitFor(() =>
      expect(
        within(screen.getByTestId('detail-processing')).getByRole('progressbar').props
          .accessibilityValue.now,
      ).toBe(60),
    );
    expect(screen.getByText('Analizando colores')).toBeTruthy();
  });

  it('asks for confirmation before deleting, then leaves for Armario', async () => {
    await renderScreen();
    await fireEvent.press(await screen.findByLabelText('Eliminar prenda'));
    expect(await screen.findByTestId('delete-confirm')).toBeTruthy();
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false);

    await fireEvent.press(screen.getByLabelText('Cancelar'));
    await waitFor(() => expect(screen.queryByTestId('delete-confirm')).toBeNull());

    await fireEvent.press(screen.getByLabelText('Eliminar prenda'));
    await fireEvent.press(await screen.findByLabelText('Eliminar definitivamente'));
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/(tabs)/wardrobe'));
    expect(calls.filter((c) => c.method === 'DELETE')).toHaveLength(1);
  });

  it('shows the API message on 409 GARMENT_HAS_HISTORY and stays on the screen', async () => {
    deleteResponse = () =>
      json(
        {
          error: {
            code: 'GARMENT_HAS_HISTORY',
            message: 'La prenda aparece en outfits; archívala en su lugar.',
            details: null,
          },
        },
        409,
      );
    await renderScreen();
    await fireEvent.press(await screen.findByLabelText('Eliminar prenda'));
    await fireEvent.press(await screen.findByLabelText('Eliminar definitivamente'));
    expect(await screen.findByTestId('action-error')).toHaveTextContent(
      'La prenda aparece en outfits; archívala en su lugar.',
    );
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it('shows error with retry and a not-found state', async () => {
    globalThis.fetch = jest.fn(() =>
      Promise.resolve(
        json({ error: { code: 'GARMENT_NOT_FOUND', message: 'x', details: null } }, 404),
      ),
    ) as unknown as typeof fetch;
    await renderScreen();
    expect(await screen.findByText('No encontramos esta prenda')).toBeTruthy();
    await cleanup();

    globalThis.fetch = jest.fn(() =>
      Promise.resolve(json({ error: { code: 'E', message: 'Sin conexión', details: null } }, 500)),
    ) as unknown as typeof fetch;
    await renderScreen();
    expect(await screen.findByTestId('error-state')).toBeTruthy();
  });
});
