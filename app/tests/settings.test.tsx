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
import type { ReactNode } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import SettingsScreen from '../app/settings';
import { SAVED_NOTE_MS } from '../src/components/ModelSettingsCard';
import { reportUnreachable, resetBackendStatus } from '../src/offline/reachability';

jest.mock('expo-router', () => ({
  useRouter: () => ({ replace: jest.fn(), back: jest.fn(), canGoBack: () => false }),
}));

const clients: QueryClient[] = [];

function renderWithClient(ui: ReactNode) {
  // gcTime 0 (queries and mutations) so no garbage-collection timer outlives the test.
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false, gcTime: 0 },
    },
  });
  clients.push(client);
  return render(
    <SafeAreaProvider
      initialMetrics={{
        frame: { x: 0, y: 0, width: 390, height: 844 },
        insets: { top: 0, left: 0, right: 0, bottom: 0 },
      }}
    >
      <QueryClientProvider client={client}>{ui}</QueryClientProvider>
    </SafeAreaProvider>,
  );
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

const SETTINGS = {
  weight_color: 0.3,
  weight_style: 0.3,
  weight_novelty: 0.2,
  weight_preference: 0.2,
  no_repeat_days: 7,
  max_accessories: 2,
  tryon_gender: 'woman',
  tryon_skin_tone: 3,
  duplicate_warning_threshold: 0.9,
  needs_review_threshold: 0.7,
  color_review_threshold: 0.6,
};

type Handler = (request: Request) => Response | Promise<Response>;

/** Routes the mocked fetch by "METHOD /path"; unrouted requests fail with a network error. */
function routeFetch(routes: Record<string, Handler | Response>) {
  (globalThis.fetch as jest.Mock).mockImplementation(async (request: Request) => {
    const key = `${request.method} ${new URL(request.url).pathname}`;
    const route = routes[key];
    if (!route) throw new Error(`unrouted ${key}`);
    return typeof route === 'function' ? route(request) : route.clone();
  });
}

const fetchCalls = (key: string) =>
  (globalThis.fetch as jest.Mock).mock.calls.filter(
    ([request]: [Request]) => `${request.method} ${new URL(request.url).pathname}` === key,
  );

describe('SettingsScreen', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = jest.fn();
  });

  afterEach(async () => {
    await cleanup();
    resetBackendStatus();
    clients.splice(0).forEach((client) => client.clear());
    globalThis.fetch = originalFetch;
  });

  it('titles the page and offers a way back, since the native header is hidden', async () => {
    routeFetch({ 'GET /health': json({ status: 'ok' }), 'GET /settings': json(SETTINGS) });

    await renderWithClient(<SettingsScreen />);

    expect(screen.getByRole('header', { name: 'Ajustes' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Volver' })).toBeTruthy();
  });

  describe('connection status (UI-REQ-014)', () => {
    it('shows the connected line when /health succeeds', async () => {
      routeFetch({ 'GET /health': json({ status: 'ok' }), 'GET /settings': json(SETTINGS) });

      await renderWithClient(<SettingsScreen />);

      expect(await screen.findByText('Conectado al servidor')).toBeTruthy();
    });

    it('shows an error with retry on an HTTP 5xx with an empty body (UI-REQ-008)', async () => {
      routeFetch({
        'GET /health': new Response('', { status: 503 }),
        'GET /settings': json(SETTINGS),
      });

      await renderWithClient(<SettingsScreen />);

      const connection = await screen.findByTestId('settings-connection');
      await waitFor(() => {
        expect(within(connection).getByRole('button', { name: 'Reintentar' })).toBeTruthy();
      });
      expect(screen.queryByText('Conectado al servidor')).toBeNull();
    });

    it('shows an error with retry when /health fails, and recovers on retry', async () => {
      let healthy = false;
      routeFetch({
        'GET /health': () => {
          if (!healthy) throw new Error('network error');
          return json({ status: 'ok' });
        },
        'GET /settings': json(SETTINGS),
      });

      await renderWithClient(<SettingsScreen />);

      const connection = await screen.findByTestId('settings-connection');
      const retry = await within(connection).findByRole('button', { name: 'Reintentar' });
      healthy = true;
      await fireEvent.press(retry);

      expect(await screen.findByText('Conectado al servidor')).toBeTruthy();
      expect(fetchCalls('GET /health')).toHaveLength(2);
    });
  });

  describe('engine settings (API-REQ-014/015)', () => {
    beforeEach(() => {
      routeFetch({ 'GET /health': json({ status: 'ok' }), 'GET /settings': json(SETTINGS) });
    });

    it('shows the loaded values in editable fields', async () => {
      await renderWithClient(<SettingsScreen />);

      expect((await screen.findByLabelText('Peso de color')).props.value).toBe('0.3');
      expect(screen.getByLabelText('Peso de estilo').props.value).toBe('0.3');
      expect(screen.getByLabelText('Peso de novedad').props.value).toBe('0.2');
      expect(screen.getByLabelText('Peso de preferencia').props.value).toBe('0.2');
      expect(screen.getByLabelText('Días sin repetir').props.value).toBe('7');
      expect(screen.getByLabelText('Máximo de complementos').props.value).toBe('2');
      expect(screen.getByTestId('weight-sum').props.children).toContain('Suma de pesos: 1,00');
    });

    it('shows an error with retry when settings fail to load, and recovers', async () => {
      let ok = false;
      routeFetch({
        'GET /health': json({ status: 'ok' }),
        'GET /settings': () =>
          ok ? json(SETTINGS) : json({ error: { code: 'X', message: 'boom' } }, 500),
      });
      await renderWithClient(<SettingsScreen />);

      const engine = await screen.findByTestId('settings-engine');
      const retry = await within(engine).findByRole('button', { name: 'Reintentar' });
      expect(within(engine).getByText('No se pudieron cargar los ajustes.')).toBeTruthy();
      ok = true;
      await fireEvent.press(retry);

      expect(await screen.findByLabelText('Peso de color')).toBeTruthy();
    });

    it('PATCHes the edited values and confirms the save', async () => {
      const saved = { ...SETTINGS, weight_color: 0.4, weight_style: 0.2, no_repeat_days: 10 };
      let body: unknown;
      routeFetch({
        'GET /health': json({ status: 'ok' }),
        'GET /settings': json(SETTINGS),
        'PATCH /settings': async (request) => {
          body = await request.json();
          return json(saved);
        },
      });
      await renderWithClient(<SettingsScreen />);

      await fireEvent.changeText(await screen.findByLabelText('Peso de color'), '0,4');
      await fireEvent.changeText(screen.getByLabelText('Peso de estilo'), '0.2');
      await fireEvent.changeText(screen.getByLabelText('Días sin repetir'), '10');
      await fireEvent.press(screen.getByRole('button', { name: 'Guardar' }));

      expect(await screen.findByText('Ajustes guardados')).toBeTruthy();
      expect(body).toEqual({
        weight_color: 0.4,
        weight_style: 0.2,
        weight_novelty: 0.2,
        weight_preference: 0.2,
        no_repeat_days: 10,
        max_accessories: 2,
      });
      expect(screen.getByLabelText('Peso de color').props.value).toBe('0.4');
    });

    it('validates on the client and does not call the API', async () => {
      await renderWithClient(<SettingsScreen />);

      await fireEvent.changeText(await screen.findByLabelText('Peso de color'), '1.5');
      await fireEvent.changeText(screen.getByLabelText('Días sin repetir'), '-1');
      await fireEvent.changeText(screen.getByLabelText('Máximo de complementos'), '2.5');
      await fireEvent.press(screen.getByRole('button', { name: 'Guardar' }));

      expect(await screen.findByText('Introduce un número entre 0 y 1.')).toBeTruthy();
      expect(screen.getAllByText('Introduce un número entero igual o mayor que 0.')).toHaveLength(
        2,
      );
      expect(fetchCalls('PATCH /settings')).toHaveLength(0);

      await fireEvent.changeText(screen.getByLabelText('Peso de color'), '0.3');
      expect(screen.queryByText('Introduce un número entre 0 y 1.')).toBeNull();
      expect(screen.getAllByText('Introduce un número entero igual o mayor que 0.')).toHaveLength(
        2,
      );
    });

    it('rejects weights that do not sum to 1 before calling the API', async () => {
      await renderWithClient(<SettingsScreen />);

      await fireEvent.changeText(await screen.findByLabelText('Peso de color'), '0.9');
      await fireEvent.press(screen.getByRole('button', { name: 'Guardar' }));

      expect(
        await screen.findByText('Los pesos deben sumar 1,00 (ahora suman 1,60).'),
      ).toBeTruthy();
      expect(fetchCalls('PATCH /settings')).toHaveLength(0);

      await fireEvent.changeText(screen.getByLabelText('Peso de color'), '0.3');
      expect(screen.queryByText(/Los pesos deben sumar/)).toBeNull();
    });

    it('shows the API INVALID_WEIGHTS message inline and keeps the edited values', async () => {
      routeFetch({
        'GET /health': json({ status: 'ok' }),
        'GET /settings': json(SETTINGS),
        'PATCH /settings': json(
          {
            error: {
              code: 'INVALID_WEIGHTS',
              message: 'Los pesos deben sumar 1.0 (±0.01).',
              details: null,
            },
          },
          400,
        ),
      });
      await renderWithClient(<SettingsScreen />);

      await fireEvent.changeText(await screen.findByLabelText('Peso de color'), '0.305');
      await fireEvent.changeText(screen.getByLabelText('Peso de estilo'), '0.3');
      await fireEvent.press(screen.getByRole('button', { name: 'Guardar' }));

      expect(await screen.findByText('Los pesos deben sumar 1.0 (±0.01).')).toBeTruthy();
      expect(screen.queryByText('Ajustes guardados')).toBeNull();
      expect(screen.getByLabelText('Peso de color').props.value).toBe('0.305');
    });
  });

  describe('"Tu modelo" card', () => {
    const TONES = [
      { id: 1, hex: '#F3DBC8' },
      { id: 2, hex: '#E5BF9E' },
      { id: 3, hex: '#CF9D77' },
      { id: 4, hex: '#AE7650' },
      { id: 5, hex: '#85532F' },
      { id: 6, hex: '#583522' },
    ];
    const caps = (patch: Record<string, unknown> = {}) =>
      json({
        enabled: true,
        supported_categories: ['top', 'bottom'],
        max_passes: 3,
        genders: ['woman', 'man'],
        skin_tones: TONES,
        ...patch,
      });
    // The server keeps what was saved: the screen refetches the settings after a PATCH.
    let stored = SETTINGS;
    beforeEach(() => {
      stored = SETTINGS;
    });
    const base = (extra: Record<string, Handler | Response> = {}) =>
      routeFetch({
        'GET /health': json({ status: 'ok' }),
        'GET /settings': () => json(stored),
        'GET /tryon/capabilities': caps(),
        ...extra,
      });

    it('shows the current model: gender chosen, tone checked, six labelled radios', async () => {
      base();
      await renderWithClient(<SettingsScreen />);

      const card = await screen.findByTestId('settings-model');
      expect(within(card).getByRole('header', { name: 'Tu modelo' })).toBeTruthy();
      expect(within(card).getByRole('tab', { name: 'Mujer', selected: true })).toBeTruthy();
      expect(within(card).getByRole('tab', { name: 'Hombre', selected: false })).toBeTruthy();
      expect(within(card).getByLabelText('Tono de piel', { exact: true })).toBeTruthy();
      const radios = within(card).getAllByRole('radio');
      expect(radios.map((radio) => radio.props.accessibilityLabel)).toEqual(
        TONES.map((tone) => `Tono ${tone.id} de 6`),
      );
      expect(within(card).getByRole('radio', { name: 'Tono 3 de 6', checked: true })).toBeTruthy();
      expect(within(card).getAllByRole('radio', { checked: true })).toHaveLength(1);
      expect(within(card).getByLabelText('Modelo mujer, tono 3 de 6')).toBeTruthy();
    });

    it('PATCHes the tone, shows it at once and confirms with "Guardado"', async () => {
      let body: unknown;
      base({
        'PATCH /settings': async (request) => {
          body = await request.json();
          stored = { ...SETTINGS, tryon_skin_tone: 5 };
          return json(stored);
        },
      });
      await renderWithClient(<SettingsScreen />);

      await fireEvent.press(await screen.findByRole('radio', { name: 'Tono 5 de 6' }));

      expect(await screen.findByTestId('model-saved')).toBeTruthy();
      expect(screen.getByText('Guardado')).toBeTruthy();
      expect(body).toEqual({ tryon_skin_tone: 5 });
      expect(screen.getByRole('radio', { name: 'Tono 5 de 6', checked: true })).toBeTruthy();
      expect(screen.getByLabelText('Modelo mujer, tono 5 de 6')).toBeTruthy();
    });

    it('PATCHes the gender and swaps the preview', async () => {
      let body: unknown;
      base({
        'PATCH /settings': async (request) => {
          body = await request.json();
          stored = { ...SETTINGS, tryon_gender: 'man' };
          return json(stored);
        },
      });
      await renderWithClient(<SettingsScreen />);

      await fireEvent.press(await screen.findByRole('tab', { name: 'Hombre' }));

      expect(await screen.findByTestId('model-saved')).toBeTruthy();
      expect(body).toEqual({ tryon_gender: 'man' });
      expect(screen.getByRole('tab', { name: 'Hombre', selected: true })).toBeTruthy();
      expect(screen.getByLabelText('Modelo hombre, tono 3 de 6')).toBeTruthy();
    });

    it('shows the pick while it saves, then reverts it and says why when the save fails', async () => {
      let fail!: () => void;
      base({
        'PATCH /settings': () =>
          new Promise<Response>((resolve) => {
            fail = () =>
              resolve(
                json({ error: { code: 'X', message: 'Servidor caído', details: null } }, 500),
              );
          }),
      });
      await renderWithClient(<SettingsScreen />);

      await fireEvent.press(await screen.findByRole('radio', { name: 'Tono 6 de 6' }));
      expect(screen.getByRole('radio', { name: 'Tono 6 de 6', checked: true })).toBeTruthy();

      await waitFor(() => expect(fail).toBeDefined());
      await fail();

      expect(await screen.findByRole('alert')).toBeTruthy();
      expect(screen.getByText(/No se pudo guardar el cambio/)).toBeTruthy();
      expect(screen.getByRole('radio', { name: 'Tono 3 de 6', checked: true })).toBeTruthy();
      expect(screen.getByRole('radio', { name: 'Tono 6 de 6', checked: false })).toBeTruthy();
      expect(screen.queryByTestId('model-saved')).toBeNull();
    });

    it('does not save the option that is already chosen', async () => {
      base();
      await renderWithClient(<SettingsScreen />);

      await fireEvent.press(await screen.findByRole('radio', { name: 'Tono 3 de 6' }));
      await fireEvent.press(screen.getByRole('tab', { name: 'Mujer' }));

      expect(fetchCalls('PATCH /settings')).toHaveLength(0);
    });

    it('clears "Guardado" after a few seconds', async () => {
      base({
        'PATCH /settings': () => {
          stored = { ...SETTINGS, tryon_skin_tone: 5 };
          return json(stored);
        },
      });
      await renderWithClient(<SettingsScreen />);
      await fireEvent.press(await screen.findByRole('radio', { name: 'Tono 5 de 6' }));
      expect(await screen.findByTestId('model-saved')).toBeTruthy();

      jest.useFakeTimers();
      try {
        // The timer starts at the render that showed the note, so re-arm it under fake timers.
        await fireEvent.press(screen.getByRole('radio', { name: 'Tono 2 de 6' }));
        await waitFor(() => expect(fetchCalls('PATCH /settings')).toHaveLength(2));
        await act(async () => {
          await jest.advanceTimersByTimeAsync(50);
        });
        expect(screen.getByTestId('model-saved')).toBeTruthy();

        await act(async () => {
          await jest.advanceTimersByTimeAsync(SAVED_NOTE_MS - 100);
        });
        expect(screen.getByTestId('model-saved')).toBeTruthy();

        await act(async () => {
          await jest.advanceTimersByTimeAsync(200);
        });
        expect(screen.queryByTestId('model-saved')).toBeNull();
      } finally {
        jest.useRealTimers();
      }
    });

    it('sends nothing when offline: the tones and genders are disabled', async () => {
      base();
      await renderWithClient(<SettingsScreen />);
      const radio = await screen.findByRole('radio', { name: 'Tono 5 de 6' });
      await act(async () => {
        reportUnreachable();
      });

      await fireEvent.press(radio);
      await fireEvent.press(screen.getByRole('tab', { name: 'Hombre' }));

      expect(screen.getByRole('radio', { name: 'Tono 5 de 6' }).props.accessibilityState).toEqual(
        expect.objectContaining({ disabled: true }),
      );
      expect(fetchCalls('PATCH /settings')).toHaveLength(0);
      expect(screen.getByRole('radio', { name: 'Tono 3 de 6', checked: true })).toBeTruthy();
      expect(screen.getByRole('tab', { name: 'Mujer', selected: true })).toBeTruthy();
    });

    it('is hidden while the try-on is off', async () => {
      base({ 'GET /tryon/capabilities': caps({ enabled: false }) });
      await renderWithClient(<SettingsScreen />);

      expect(await screen.findByLabelText('Peso de color')).toBeTruthy();
      await waitFor(() => expect(fetchCalls('GET /tryon/capabilities')).toHaveLength(1));
      expect(screen.queryByTestId('settings-model')).toBeNull();
    });

    it('offers only the genders the server lists', async () => {
      base({ 'GET /tryon/capabilities': caps({ genders: ['woman'] }) });
      await renderWithClient(<SettingsScreen />);

      const card = await screen.findByTestId('settings-model');
      expect(within(card).queryByRole('tab')).toBeNull();
      expect(within(card).getAllByRole('radio')).toHaveLength(6);
    });
  });
});
