import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react-native';

import { ProgressBar } from '../src/components/add/ProgressBar';
import { ScanLine } from '../src/components/add/ScanLine';
import { uploadStatus } from '../src/components/add/upload-status';
import { UploadItem } from '../src/components/UploadItem';

const mockReduced = jest.fn(() => false);
jest.mock('../src/hooks/useReducedMotion', () => ({ useReducedMotion: () => mockReduced() }));
jest.mock('expo-router', () => ({ useRouter: () => ({ push: jest.fn() }) }));

describe('uploadStatus', () => {
  it('maps queue phases and job states to the state pill', () => {
    expect(uploadStatus('preparing')).toMatchObject({ label: 'Subiendo', progress: null });
    expect(uploadStatus('uploading')).toMatchObject({ label: 'Subiendo', progress: null });
    expect(uploadStatus('queued')).toMatchObject({ label: 'En cola', tone: 'ghost', progress: 0 });
    expect(uploadStatus('queued', { status: 'pending', step: null, progress: 0 }).label).toBe(
      'En cola',
    );
    expect(uploadStatus('queued', { status: 'running', step: 'cutout', progress: 30 })).toEqual({
      kind: 'analysing',
      label: 'Analizando',
      tone: 'info',
      step: 'Recortando',
      progress: 30,
    });
    expect(uploadStatus('queued', { status: 'done', step: 'consolidate', progress: 100 })).toEqual({
      kind: 'done',
      label: 'Lista',
      tone: 'ok',
      step: null,
      progress: 100,
    });
    expect(
      uploadStatus('queued', { status: 'failed', step: 'cutout', progress: 30 }),
    ).toMatchObject({
      label: 'Error',
      tone: 'warn',
    });
    expect(uploadStatus('error')).toMatchObject({ label: 'Error', tone: 'warn' });
  });
});

describe('ProgressBar', () => {
  beforeEach(() => mockReduced.mockReturnValue(false));

  it('is determinate when the progress is known and clamps it', async () => {
    await render(<ProgressBar value={42} label="Progreso" />);
    expect(screen.getByRole('progressbar').props.accessibilityValue).toEqual({
      min: 0,
      max: 100,
      now: 42,
    });
    expect(screen.getByTestId('progress-fill')).toBeTruthy();
    await cleanup();
    await render(<ProgressBar value={140} label="Progreso" />);
    expect(screen.getByRole('progressbar').props.accessibilityValue.now).toBe(100);
  });

  it('is indeterminate without a value: no `now`, an animated sweep', async () => {
    await render(<ProgressBar value={null} label="Subiendo" />);
    const value = screen.getByRole('progressbar').props.accessibilityValue;
    expect(value.now).toBeUndefined();
    expect(screen.getByTestId('progress-sweep')).toBeTruthy();
    expect(screen.queryByTestId('progress-fill')).toBeNull();
  });

  it('rests still under reduced motion', async () => {
    mockReduced.mockReturnValue(true);
    await render(<ProgressBar value={null} label="Subiendo" />);
    expect(screen.getByTestId('progress-sweep-static')).toBeTruthy();
    expect(screen.queryByTestId('progress-sweep')).toBeNull();
  });
});

describe('ScanLine', () => {
  it('moves normally and is static under reduced motion', async () => {
    mockReduced.mockReturnValue(false);
    await render(<ScanLine />);
    expect(screen.getByTestId('scan-line', { includeHiddenElements: true })).toBeTruthy();
    await cleanup();
    mockReduced.mockReturnValue(true);
    await render(<ScanLine />);
    expect(screen.getByTestId('scan-line-static', { includeHiddenElements: true })).toBeTruthy();
    expect(screen.queryByTestId('scan-line', { includeHiddenElements: true })).toBeNull();
  });
});

describe('UploadItem done state', () => {
  const originalFetch = globalThis.fetch;
  afterEach(async () => {
    await cleanup();
    globalThis.fetch = originalFetch;
  });

  const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });

  it('shows the composed name, category, colours, confidence and Revisar', async () => {
    globalThis.fetch = jest.fn(async (request: Request) => {
      const path = new URL(request.url).pathname;
      if (path === '/jobs/j1') {
        return json({
          status: 'done',
          step: 'consolidate',
          progress: 100,
          error: null,
          result: null,
        });
      }
      return json({
        id: 'g1',
        category: 'top',
        subcategory: 'camiseta',
        colors: [{ name: 'azul', hex: '#3E6A8A' }],
        material: null,
        img_cutout: 'cutout/g1.png',
        img_thumb: 'thumb/g1.png',
        ai_confidence: { category: { value: 'top', confidence: 0.92, source: 'local' } },
      });
    }) as jest.Mock;
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    await render(
      <QueryClientProvider client={client}>
        <UploadItem
          item={{ key: 'k', name: 'a.jpg', phase: 'queued', jobId: 'j1', garmentId: 'g1' }}
          onRetryUpload={jest.fn()}
          onDismiss={jest.fn()}
        />
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Camiseta azul')).toBeTruthy();
    expect(screen.getByText('Lista')).toBeTruthy();
    expect(screen.getByText('Top')).toBeTruthy();
    expect(screen.getByText('92 % seguro')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Revisar a.jpg' })).toBeTruthy();
    // The bar is gone once the photo is done.
    await waitFor(() => expect(screen.queryByRole('progressbar')).toBeNull());
    client.clear();
  });

  describe('while the garment details are missing', () => {
    const doneJob = {
      status: 'done',
      step: 'consolidate',
      progress: 100,
      error: null,
      result: null,
    };

    async function renderDone(garmentResponse: () => Response | Promise<Response>) {
      globalThis.fetch = jest.fn(async (request: Request) =>
        new URL(request.url).pathname === '/jobs/j1' ? json(doneJob) : garmentResponse(),
      ) as jest.Mock;
      const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
      await render(
        <QueryClientProvider client={client}>
          <UploadItem
            item={{ key: 'k', name: 'a.jpg', phase: 'queued', jobId: 'j1', garmentId: 'g1' }}
            onRetryUpload={jest.fn()}
            onDismiss={jest.fn()}
          />
        </QueryClientProvider>,
      );
      return client;
    }

    it('shows the file name once while the garment loads, with Revisar usable', async () => {
      const client = await renderDone(() => new Promise<Response>(() => {}));

      expect(await screen.findByText('Lista')).toBeTruthy();
      expect(screen.getAllByText('a.jpg')).toHaveLength(1);
      expect(screen.queryByText(/No se pudieron cargar/)).toBeNull();
      expect(screen.getByRole('button', { name: 'Revisar a.jpg' })).toBeTruthy();
      client.clear();
    });

    it('keeps the loaded details, with no error, when a background refetch fails', async () => {
      let ok = true;
      const client = await renderDone(() =>
        ok
          ? json({ id: 'g1', category: 'top', subcategory: 'camiseta', colors: [] })
          : json({ error: { code: 'X', message: 'boom' } }, 500),
      );
      expect(await screen.findByText('Camiseta')).toBeTruthy();

      ok = false;
      await act(async () => {
        await client.refetchQueries({ queryKey: ['garments'] });
      });

      await waitFor(() => expect(client.isFetching()).toBe(0));
      expect(screen.getByText('Camiseta')).toBeTruthy();
      expect(screen.queryByText(/No se pudieron cargar/)).toBeNull();
      expect(screen.queryByRole('button', { name: 'Reintentar detalles de a.jpg' })).toBeNull();
      client.clear();
    });

    it('shows an inline error with retry when the garment fails, keeping Revisar', async () => {
      let ok = false;
      const client = await renderDone(() =>
        ok
          ? json({ id: 'g1', category: 'top', subcategory: 'camiseta', colors: [] })
          : json({ error: { code: 'X', message: 'boom' } }, 500),
      );

      expect(
        await screen.findByText('No se pudieron cargar los detalles de la prenda.'),
      ).toBeTruthy();
      expect(screen.getAllByText('a.jpg')).toHaveLength(1);
      expect(screen.getByRole('button', { name: 'Revisar a.jpg' })).toBeTruthy();

      ok = true;
      await fireEvent.press(screen.getByRole('button', { name: 'Reintentar detalles de a.jpg' }));
      expect(await screen.findByText('Camiseta')).toBeTruthy();
      expect(screen.queryByText(/No se pudieron cargar/)).toBeNull();
      client.clear();
    });
  });
});
