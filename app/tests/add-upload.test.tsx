import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react-native';

import { SafeAreaProvider } from 'react-native-safe-area-context';

import { getItem } from '../src/lib/device-storage';

const mockPush = jest.fn();
jest.mock('expo-router', () => ({ useRouter: () => ({ push: mockPush }) }));
jest.mock('../src/lib/device-storage', () => ({
  getItem: jest.fn(),
  setItem: jest.fn(),
}));
jest.mock('expo-image-picker', () => ({
  requestCameraPermissionsAsync: jest.fn(),
  launchCameraAsync: jest.fn(),
  launchImageLibraryAsync: jest.fn(),
}));
const mockResize = jest.fn();
jest.mock('expo-image-manipulator', () => ({
  SaveFormat: { JPEG: 'jpeg' },
  ImageManipulator: {
    manipulate: () => {
      const context = {
        resize: (size: unknown) => {
          mockResize(size);
          return context;
        },
        renderAsync: async () => ({
          saveAsync: async () => ({ uri: 'file:///out.jpg', width: 2048, height: 1365 }),
        }),
      };
      return context;
    },
  },
}));

// eslint-disable-next-line @typescript-eslint/no-require-imports
const ImagePicker = require('expo-image-picker');
const metrics = {
  frame: { x: 0, y: 0, width: 390, height: 844 },
  insets: { top: 0, left: 0, right: 0, bottom: 0 },
};

// eslint-disable-next-line @typescript-eslint/no-require-imports
const AddScreen = require('../app/(tabs)/add').default;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

type Handler = (request: Request) => Response | undefined;

/** Routes the mocked fetch by "METHOD /path"; later routes override earlier. */
function routeFetch(routes: Record<string, Handler | Response>) {
  (globalThis.fetch as jest.Mock).mockImplementation(async (request: Request) => {
    const key = `${request.method} ${new URL(request.url).pathname}`;
    const route = routes[key];
    const response = typeof route === 'function' ? route(request) : route?.clone();
    return response ?? json({ error: { code: 'X', message: `unrouted ${key}` } }, 500);
  });
}

const job = (status: string, step: string | null, progress: number, error: string | null = null) =>
  json({ status, step, progress, error, result: null });

const asset = (fileName: string, width = 3000, height = 2000) => ({
  uri: `file:///${fileName}`,
  width,
  height,
  fileName,
});

async function renderScreen() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { gcTime: 0 } },
  });
  const view = await render(
    <SafeAreaProvider initialMetrics={metrics}>
      <QueryClientProvider client={client}>
        <AddScreen />
      </QueryClientProvider>
    </SafeAreaProvider>,
  );
  return { client, ...view };
}

describe('AddScreen upload flow', () => {
  const originalFetch = globalThis.fetch;
  let client: QueryClient | undefined;

  beforeEach(() => {
    globalThis.fetch = jest.fn();
    jest.clearAllMocks();
    mockPush.mockReset();
    mockResize.mockReset();
    (getItem as jest.Mock).mockResolvedValue('true'); // tips already seen
    ImagePicker.requestCameraPermissionsAsync.mockResolvedValue({ granted: true });
  });

  afterEach(async () => {
    await cleanup();
    client?.clear();
    client = undefined;
    globalThis.fetch = originalFetch;
  });

  async function pickTwoFromGallery() {
    ImagePicker.launchImageLibraryAsync.mockResolvedValue({
      canceled: false,
      assets: [asset('a.jpg'), asset('b.jpg', 1000, 1500)],
    });
    await fireEvent.press(screen.getByRole('button', { name: 'Elegir de la galería' }));
  }

  it('resizes to 2048 and shows independent progress per photo', async () => {
    let created = 0;
    routeFetch({
      'POST /garments': () => {
        created += 1;
        return json({ garment_id: `g${created}`, job_id: `j${created}` }, 202);
      },
      'GET /jobs/j1': job('running', 'cutout', 30),
      'GET /jobs/j2': job('running', 'color', 60),
    });
    ({ client } = await renderScreen());

    await pickTwoFromGallery();

    await waitFor(() => {
      expect(screen.getByText('Recortando')).toBeTruthy();
      expect(screen.getByText('Analizando colores')).toBeTruthy();
    });
    expect(screen.getAllByText('Analizando')).toHaveLength(2);
    const bars = screen.getAllByRole('progressbar');
    expect(bars.map((bar) => bar.props.accessibilityValue.now).sort()).toEqual([30, 60]);
    // Landscape resized by width, portrait by height (long side 3000/1500 -> 2048 only for a.jpg).
    expect(mockResize).toHaveBeenCalledTimes(1);
    expect(mockResize).toHaveBeenCalledWith({ width: 2048 });
  });

  it('warns on low-resolution photos but still uploads them', async () => {
    routeFetch({
      'POST /garments': () => json({ garment_id: 'g1', job_id: 'j1' }, 202),
      'GET /jobs/j1': job('running', 'cutout', 30),
    });
    ({ client } = await renderScreen());
    ImagePicker.launchImageLibraryAsync.mockResolvedValue({
      canceled: false,
      assets: [asset('small.jpg', 417, 300), asset('big.jpg', 3000, 2000)],
    });
    await fireEvent.press(screen.getByRole('button', { name: 'Elegir de la galería' }));

    await waitFor(() => expect(screen.getAllByRole('progressbar').length).toBeGreaterThan(0));
    const notes = screen.getAllByTestId('low-res-note');
    expect(notes).toHaveLength(1);
    expect(screen.getByText(/Foto de baja resolución: se verá borrosa/)).toBeTruthy();
    await waitFor(() => expect(screen.getAllByText('Recortando').length).toBe(2));
  });

  it('keeps the low-resolution note on a failed upload and after a retry', async () => {
    let attempts = 0;
    routeFetch({
      'POST /garments': () =>
        ++attempts === 1
          ? json({ error: { code: 'X', message: 'Sin conexión con el servidor.' } }, 500)
          : json({ garment_id: 'g1', job_id: 'j1' }, 202),
      'GET /jobs/j1': job('running', 'cutout', 30),
    });
    ({ client } = await renderScreen());
    ImagePicker.launchImageLibraryAsync.mockResolvedValue({
      canceled: false,
      assets: [asset('small.jpg', 417, 300)],
    });
    await fireEvent.press(screen.getByRole('button', { name: 'Elegir de la galería' }));

    const retry = await screen.findByRole('button', { name: 'Reintentar subida de small.jpg' });
    expect(screen.getAllByTestId('low-res-note')).toHaveLength(1);

    await fireEvent.press(retry);
    await waitFor(() => expect(screen.getAllByRole('progressbar').length).toBeGreaterThan(0));
    expect(attempts).toBe(2);
    expect(screen.getAllByTestId('low-res-note')).toHaveLength(1);
  });

  it('lets the user add more photos while others are processing', async () => {
    let created = 0;
    routeFetch({
      'POST /garments': () => {
        created += 1;
        return json({ garment_id: `g${created}`, job_id: `j${created}` }, 202);
      },
      'GET /jobs/j1': job('running', 'cutout', 30),
      'GET /jobs/j2': job('pending', null, 0),
    });
    ({ client } = await renderScreen());

    ImagePicker.launchImageLibraryAsync.mockResolvedValue({
      canceled: false,
      assets: [asset('a.jpg')],
    });
    await fireEvent.press(screen.getByRole('button', { name: 'Elegir de la galería' }));
    await waitFor(() => expect(screen.getByText('Recortando')).toBeTruthy());

    ImagePicker.launchCameraAsync.mockResolvedValue({
      canceled: false,
      assets: [asset('b.jpg')],
    });
    await fireEvent.press(screen.getByRole('button', { name: 'Hacer foto' }));

    await waitFor(() => expect(screen.getByText('En cola')).toBeTruthy());
    expect(screen.getByText('Recortando')).toBeTruthy();
  });

  it('done shows Revisar and navigates to the review screen only on press', async () => {
    routeFetch({
      'POST /garments': json({ garment_id: 'g1', job_id: 'j1' }, 202),
      'GET /jobs/j1': job('done', 'consolidate', 100),
    });
    ({ client } = await renderScreen());
    ImagePicker.launchImageLibraryAsync.mockResolvedValue({
      canceled: false,
      assets: [asset('a.jpg')],
    });
    await fireEvent.press(screen.getByRole('button', { name: 'Elegir de la galería' }));

    const review = await screen.findByRole('button', { name: 'Revisar a.jpg' });
    expect(mockPush).not.toHaveBeenCalled();
    await fireEvent.press(review);
    expect(mockPush).toHaveBeenCalledWith('/review/g1');
  });

  it('failed shows the job error and Reintentar resumes processing', async () => {
    let retried = false;
    const retry = jest.fn(() => {
      retried = true;
      return job('pending', null, 0);
    });
    routeFetch({
      'POST /garments': json({ garment_id: 'g1', job_id: 'j1' }, 202),
      'GET /jobs/j1': () =>
        retried
          ? job('running', 'cutout', 30)
          : job('failed', 'cutout', 30, 'No se pudo recortar la prenda.'),
      'POST /garments/g1/retry': retry,
    });
    ({ client } = await renderScreen());
    ImagePicker.launchImageLibraryAsync.mockResolvedValue({
      canceled: false,
      assets: [asset('a.jpg')],
    });
    await fireEvent.press(screen.getByRole('button', { name: 'Elegir de la galería' }));

    expect(await screen.findByText('No se pudo recortar la prenda.')).toBeTruthy();
    await fireEvent.press(screen.getByRole('button', { name: 'Reintentar a.jpg' }));

    await waitFor(() => expect(retry).toHaveBeenCalledTimes(1));
    // The job is refetched and the item goes back to processing with progress.
    expect(await screen.findByText('Recortando')).toBeTruthy();
    expect(screen.getByRole('progressbar').props.accessibilityValue.now).toBe(30);
    expect(screen.queryByText('No se pudo recortar la prenda.')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reintentar a.jpg' })).toBeNull();
  });

  it('shows the API error inline when the upload is rejected (400)', async () => {
    routeFetch({
      'POST /garments': json(
        { error: { code: 'INVALID_IMAGE', message: 'La imagen no es válida.', details: null } },
        400,
      ),
    });
    ({ client } = await renderScreen());
    ImagePicker.launchImageLibraryAsync.mockResolvedValue({
      canceled: false,
      assets: [asset('a.jpg')],
    });
    await fireEvent.press(screen.getByRole('button', { name: 'Elegir de la galería' }));

    expect(await screen.findByText('La imagen no es válida.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Reintentar subida de a.jpg' })).toBeTruthy();
  });

  it('shows a Spanish message when camera permission is denied', async () => {
    ImagePicker.requestCameraPermissionsAsync.mockResolvedValue({ granted: false });
    ({ client } = await renderScreen());

    await fireEvent.press(screen.getByRole('button', { name: 'Hacer foto' }));

    expect(await screen.findByText(/permiso para usar la cámara/)).toBeTruthy();
    expect(ImagePicker.launchCameraAsync).not.toHaveBeenCalled();
  });
});
