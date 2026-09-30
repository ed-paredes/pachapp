import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react-native';
import type { ReactNode } from 'react';

import SettingsScreen from '../app/settings';

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
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
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
    clients.splice(0).forEach((client) => client.clear());
    globalThis.fetch = originalFetch;
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
});
