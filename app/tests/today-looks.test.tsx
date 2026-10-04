import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { AccessibilityInfo, Platform } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { queryKeys } from '../src/api-client/query-keys';
import { OFFLINE_NOTE } from '../src/components/OfflineBanner';
import { ToastProvider } from '../src/components/ui';
import { bumpWardrobeVersion, proposalSet } from '../src/hooks/useGenerateOutfits';
import { localDateKey, msUntilEndOfDay } from '../src/lib/look-day';
import { reportUnreachable, resetBackendStatus } from '../src/offline/reachability';

const mockPush = jest.fn();
jest.mock('expo-router', () => ({ useRouter: () => ({ push: mockPush }) }));
jest.mock('../src/offline/sync', () => ({ syncWardrobe: jest.fn() }));

// eslint-disable-next-line @typescript-eslint/no-require-imports
const TodayScreen = require('../app/(tabs)/index').default;

const realOS = Platform.OS;
const realFetch = globalThis.fetch;
const setPlatform = (os: string) =>
  Object.defineProperty(Platform, 'OS', { configurable: true, get: () => os });
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

/** Five looks: top n + bottom n + shoes n, with n = 1..5 (plus a second batch, n = 6..10). */
const slotsOf = (n: number) =>
  [
    { id: `t${n}`, slot: 'top', layer: 2 },
    { id: `b${n}`, slot: 'bottom', layer: 3 },
    { id: `s${n}`, slot: 'shoes', layer: 4 },
  ].map(({ id, slot, layer }) => ({ garment_id: id, slot, layer }));

const proposalOf = (n: number, explanation = `Look número ${n} coherente de arriba abajo.`) => ({
  items: slotsOf(n),
  score: 0.9 - n / 100,
  score_breakdown: { color: 0.5, style: 0.5, novelty: 0.5, preference: 0, total: 0.9 - n / 100 },
  explanation,
});

const batch = (from: number, count = 5) => ({
  proposals: Array.from({ length: count }, (_, i) => proposalOf(from + i)),
  generated_at: '2026-10-04T08:00:00Z',
});

const CATEGORY: Record<string, string> = { t: 'top', b: 'bottom', s: 'shoes' };
const detail = (id: string) => ({
  id,
  category: CATEGORY[id[0]],
  subcategory: null,
  colors: [{ name: 'negro', hex: '#222222', lab: [10, 0, 0], proportion: 1 }],
  status: 'active',
  img_thumb: `thumb/${id}.webp`,
  img_cutout: `cutout/${id}.png`,
  formality: 2,
  style_tags: ['casual'],
  material: null,
});

type Call = { method: string; path: string; body: unknown };
let calls: Call[];
let generateBodies: Record<string, unknown>[];

/**
 * A small API: `batches` are answered in order to each `POST /outfits/generate`; the wear-log
 * answers come from `wearLog`.
 */
function mockApi({
  batches = [batch(1)],
  wearLog = [json({ id: 'w1', date: '2026-10-04', outfit_id: 'o1', created_at: 'x' }, 201)],
  put = json({ id: 'w1', date: '2026-10-04', outfit_id: 'o1', created_at: 'x' }),
}: { batches?: unknown[]; wearLog?: Response[]; put?: Response } = {}) {
  const queue = [...batches];
  const wearQueue = [...wearLog];
  (globalThis.fetch as jest.Mock).mockImplementation(async (request: Request) => {
    const url = new URL(request.url);
    const method = request.method;
    const body =
      method === 'POST' || method === 'PUT'
        ? await request
            .clone()
            .json()
            .catch(() => null)
        : null;
    calls.push({ method, path: url.pathname, body });
    if (url.pathname === '/outfits/generate') {
      generateBodies.push(body as Record<string, unknown>);
      return json(queue.length > 1 ? queue.shift() : queue[0]);
    }
    if (url.pathname === '/outfits') return json({ id: 'o1', items: [] }, 201);
    if (url.pathname === '/wear-log') return wearQueue.shift() ?? wearLog[0];
    if (url.pathname.startsWith('/wear-log/')) return put;
    if (url.pathname.startsWith('/garments/')) return json(detail(url.pathname.split('/')[2]));
    if (url.pathname === '/garments') {
      return json({ items: [], total: 15, page: 1, page_size: 50 });
    }
    return json({});
  });
}

const conflict = () =>
  json(
    {
      error: {
        code: 'WEAR_LOG_CONFLICT',
        message: 'Ya registraste un outfit para este día.',
        details: { date: '2026-10-03', outfit_id: 'old', wear_log_id: 'w0' },
      },
    },
    409,
  );

const clients: QueryClient[] = [];
function makeClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { gcTime: 0 } },
  });
  clients.push(client);
  return client;
}

async function renderToday(client = makeClient()) {
  await render(
    <SafeAreaProvider
      initialMetrics={{
        frame: { x: 0, y: 0, width: 390, height: 844 },
        insets: { top: 0, left: 0, right: 0, bottom: 0 },
      }}
    >
      <ToastProvider>
        <QueryClientProvider client={client}>
          <TodayScreen />
        </QueryClientProvider>
      </ToastProvider>
    </SafeAreaProvider>,
  );
  return client;
}

const lookOfTheDay = () => screen.findByText('Look número 1 coherente de arriba abajo.');
const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });

beforeEach(() => {
  globalThis.fetch = jest.fn();
  calls = [];
  generateBodies = [];
  mockPush.mockClear();
  jest.spyOn(AccessibilityInfo, 'announceForAccessibility').mockImplementation(() => undefined);
  resetBackendStatus();
});

afterEach(async () => {
  await cleanup();
  jest.restoreAllMocks();
  globalThis.fetch = realFetch;
  setPlatform(realOS);
  resetBackendStatus();
  clients.splice(0).forEach((client) => client.clear());
});

describe('Hoy: the look of the day', () => {
  it('shows the best proposal as the look of the day and the other four as alternatives', async () => {
    mockApi();
    await renderToday();

    expect(await lookOfTheDay()).toBeTruthy();
    expect(screen.getByText('Look del día')).toBeTruthy();
    expect(screen.getByText('Casual · Formalidad 2/5')).toBeTruthy();
    expect(screen.getAllByTestId('alt-looks')).toHaveLength(1);
    // 4 alternatives, titled by their lead pieces (no invented look names).
    expect(screen.getAllByRole('button', { name: /^Ver look / })).toHaveLength(4);
    // Owner decisions: no match percentage.
    expect(screen.queryByText(/% match/)).toBeNull();
    // One generation request, without exclusions.
    expect(generateBodies).toEqual([{}]);
  });

  it('promotes an alternative to the look of the day', async () => {
    mockApi();
    await renderToday();
    await lookOfTheDay();

    await fireEvent.press(screen.getAllByRole('button', { name: /^Ver look / })[1]);

    expect(await screen.findByText('Look número 3 coherente de arriba abajo.')).toBeTruthy();
    expect(screen.queryByText('Look número 1 coherente de arriba abajo.')).toBeNull();
    // The previous look becomes one of the alternatives; still 4.
    expect(screen.getAllByRole('button', { name: /^Ver look / })).toHaveLength(4);
    expect(generateBodies).toHaveLength(1);
  });

  it('opens a piece of the look in Detalle', async () => {
    mockApi();
    await renderToday();
    await lookOfTheDay();

    await fireEvent.press(screen.getAllByRole('button', { name: /^Abrir prenda / })[0]);

    expect(mockPush).toHaveBeenCalledWith(expect.stringMatching(/^\/garments\/[tbs]1$/));
  });

  it('says what a look needs when no proposal comes back', async () => {
    mockApi({ batches: [{ proposals: [], generated_at: 'x' }] });
    await renderToday();

    expect(await screen.findByTestId('no-looks-state')).toBeTruthy();
    expect(screen.getByText('Todavía no podemos armar un look')).toBeTruthy();
  });

  it('asks again when the request fails online', async () => {
    (globalThis.fetch as jest.Mock).mockImplementation(async (request: Request) => {
      const path = new URL(request.url).pathname;
      if (path === '/outfits/generate') return json({ error: { code: 'X', message: 'x' } }, 500);
      return json({ items: [], total: 15, page: 1, page_size: 50 });
    });
    await renderToday();

    expect(await screen.findByText('No pudimos preparar tu look')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Reintentar' })).toBeTruthy();
  });

  it('does not generate for an empty wardrobe', async () => {
    (globalThis.fetch as jest.Mock).mockImplementation(async () =>
      json({ items: [], total: 0, page: 1, page_size: 50 }),
    );
    await renderToday();

    await screen.findByText('Aún no tienes suficientes prendas para generar un outfit');
    expect(calls.filter((call) => call.path === '/outfits/generate')).toHaveLength(0);
  });
});

describe('Hoy: Otra sugerencia', () => {
  it('walks the cached proposals without calling the backend', async () => {
    mockApi();
    await renderToday();
    await lookOfTheDay();

    for (const n of [2, 3, 4, 5]) {
      await fireEvent.press(screen.getByRole('button', { name: 'Otra sugerencia' }));
      expect(await screen.findByText(`Look número ${n} coherente de arriba abajo.`)).toBeTruthy();
    }

    expect(generateBodies).toHaveLength(1);
  });

  it('after the fifth asks for new ones excluding every set shown, and shows the new batch', async () => {
    mockApi({ batches: [batch(1), batch(6)] });
    await renderToday();
    await lookOfTheDay();
    for (let n = 2; n <= 5; n += 1) {
      await fireEvent.press(screen.getByRole('button', { name: 'Otra sugerencia' }));
      await screen.findByText(`Look número ${n} coherente de arriba abajo.`);
    }

    await fireEvent.press(screen.getByRole('button', { name: 'Otra sugerencia' }));

    expect(await screen.findByText('Look número 6 coherente de arriba abajo.')).toBeTruthy();
    expect(generateBodies).toHaveLength(2);
    const excluded = (generateBodies[1].exclude_sets as string[][]).map((set) => set.join());
    expect(excluded).toEqual([1, 2, 3, 4, 5].map((n) => [`b${n}`, `s${n}`, `t${n}`].join()));
  });

  it('says so, calmly, when no combination is left', async () => {
    mockApi({ batches: [batch(1), { proposals: [], generated_at: 'x' }] });
    await renderToday();
    await lookOfTheDay();
    for (let n = 2; n <= 5; n += 1) {
      await fireEvent.press(screen.getByRole('button', { name: 'Otra sugerencia' }));
      await screen.findByText(`Look número ${n} coherente de arriba abajo.`);
    }

    await fireEvent.press(screen.getByRole('button', { name: 'Otra sugerencia' }));

    expect(await screen.findByText(/No quedan más combinaciones por hoy/)).toBeTruthy();
    // The look stays and the button is off: asking again would only repeat the answer.
    expect(screen.getByText('Look número 5 coherente de arriba abajo.')).toBeTruthy();
    expect(
      screen.getByRole('button', { name: 'Otra sugerencia' }).props.accessibilityState.disabled,
    ).toBe(true);
    expect(generateBodies).toHaveLength(2);
  });
});

describe('Hoy: the exclusion bound', () => {
  it('stops asking for new rounds once the API bound would be passed, keeping every old set', async () => {
    const client = makeClient();
    const date = localDateKey(new Date());
    // 3 rounds of 70 + the 5 on screen = 215 sets shown: one more request would need > 200.
    for (let round = 0; round < 3; round += 1) {
      client.setQueryData(queryKeys.outfits.generate(date, 0, round), batch(100 + round * 70, 70));
    }
    client.setQueryData(queryKeys.outfits.generate(date, 0, 3), batch(1));
    client.setQueryData(queryKeys.outfits.today(date, 0), {
      round: 3,
      current: 0,
      shown: [0, 1, 2, 3, 4],
      exhausted: false,
    });
    mockApi();
    await renderToday(client);
    await lookOfTheDay();

    expect(screen.getByText(/No quedan más combinaciones por hoy/)).toBeTruthy();
    expect(
      screen.getByRole('button', { name: 'Otra sugerencia' }).props.accessibilityState.disabled,
    ).toBe(true);
    expect(generateBodies).toHaveLength(0);
  });
});

describe('Hoy: Me lo pongo', () => {
  it('saves the outfit, logs it for today, confirms and refreshes garments and Historial', async () => {
    mockApi();
    const client = await renderToday();
    await lookOfTheDay();
    const invalidate = jest.spyOn(client, 'invalidateQueries');

    await fireEvent.press(screen.getByRole('button', { name: 'Me lo pongo' }));

    expect(await screen.findByText('Look registrado para hoy')).toBeTruthy();
    const outfit = calls.find((call) => call.method === 'POST' && call.path === '/outfits');
    expect(outfit?.body).toMatchObject({
      source: 'generated',
      items: slotsOf(1),
      score: 0.89,
      explanation: 'Look número 1 coherente de arriba abajo.',
    });
    expect(calls.find((call) => call.path === '/wear-log')?.body).toEqual({ outfit_id: 'o1' });
    const keys = invalidate.mock.calls.map(
      ([filters]) => (filters as { queryKey: unknown[] }).queryKey[0],
    );
    expect(keys).toEqual(expect.arrayContaining(['garments', 'history']));
  });

  it('asks before replacing a day that already has an outfit, then replaces it', async () => {
    mockApi({ wearLog: [conflict()] });
    await renderToday();
    await lookOfTheDay();

    await fireEvent.press(screen.getByRole('button', { name: 'Me lo pongo' }));

    expect(await screen.findByText('Hoy ya registraste otro outfit')).toBeTruthy();
    expect(screen.getByText('¿Cambiarlo por este?')).toBeTruthy();
    expect(calls.some((call) => call.method === 'PUT')).toBe(false);

    await fireEvent.press(screen.getByRole('button', { name: 'Cambiar por este' }));

    expect(await screen.findByText('Outfit de hoy cambiado')).toBeTruthy();
    const put = calls.find((call) => call.method === 'PUT');
    // The date comes from the conflict, and the outfit saved by the first attempt is reused.
    expect(put).toMatchObject({ path: '/wear-log/2026-10-03', body: { outfit_id: 'o1' } });
    expect(calls.filter((call) => call.path === '/outfits')).toHaveLength(1);
    expect(screen.queryByTestId('replace-question')).toBeNull();
  });

  it('keeps the previous outfit when the question is declined', async () => {
    mockApi({ wearLog: [conflict()] });
    await renderToday();
    await lookOfTheDay();
    await fireEvent.press(screen.getByRole('button', { name: 'Me lo pongo' }));
    await screen.findByText('Hoy ya registraste otro outfit');

    await fireEvent.press(screen.getByRole('button', { name: 'Mantener el anterior' }));

    expect(screen.queryByTestId('replace-question')).toBeNull();
    expect(calls.some((call) => call.method === 'PUT')).toBe(false);
  });

  it('treats a transient write failure as an error to retry, never as a replace question', async () => {
    mockApi({
      wearLog: [
        json(
          {
            error: {
              code: 'WEAR_LOG_WRITE_FAILED',
              message: 'No se pudo registrar el outfit. Inténtalo de nuevo.',
              details: { date: '2026-10-04' },
            },
          },
          503,
        ),
      ],
    });
    await renderToday();
    await lookOfTheDay();

    await fireEvent.press(screen.getByRole('button', { name: 'Me lo pongo' }));

    expect(
      await screen.findByText('No pudimos registrar el look. Inténtalo de nuevo.'),
    ).toBeTruthy();
    expect(screen.queryByTestId('replace-question')).toBeNull();
    expect(calls.some((call) => call.method === 'PUT')).toBe(false);
  });

  it('does not open the question for a conflict that names no existing entry', async () => {
    mockApi({
      wearLog: [
        json(
          { error: { code: 'WEAR_LOG_CONFLICT', message: 'x', details: { date: '2026-10-04' } } },
          409,
        ),
      ],
    });
    await renderToday();
    await lookOfTheDay();

    await fireEvent.press(screen.getByRole('button', { name: 'Me lo pongo' }));

    expect(
      await screen.findByText('No pudimos registrar el look. Inténtalo de nuevo.'),
    ).toBeTruthy();
    expect(screen.queryByTestId('replace-question')).toBeNull();
  });

  it('drops the question when another look comes on screen, so the earlier one is never logged', async () => {
    mockApi({ wearLog: [conflict()] });
    await renderToday();
    await lookOfTheDay();
    await fireEvent.press(screen.getByRole('button', { name: 'Me lo pongo' }));
    await screen.findByText('Hoy ya registraste otro outfit');

    await fireEvent.press(screen.getAllByRole('button', { name: /^Ver look / })[0]);

    expect(await screen.findByText('Look número 2 coherente de arriba abajo.')).toBeTruthy();
    expect(screen.queryByTestId('replace-question')).toBeNull();
    expect(calls.some((call) => call.method === 'PUT')).toBe(false);
  });

  it('says it failed, with what to do, when the wear log cannot be written', async () => {
    mockApi({
      wearLog: [json({ error: { code: 'INVALID_WEAR_DATE', message: 'x' } }, 400)],
    });
    await renderToday();
    await lookOfTheDay();

    await fireEvent.press(screen.getByRole('button', { name: 'Me lo pongo' }));

    expect(
      await screen.findByText('No pudimos registrar el look. Inténtalo de nuevo.'),
    ).toBeTruthy();
    expect(screen.queryByTestId('replace-question')).toBeNull();
  });
});

describe('Hoy offline (native)', () => {
  it('shows the saved batch, disables Me lo pongo with the usual explanation and still cycles', async () => {
    setPlatform('android');
    const client = makeClient();
    const date = localDateKey(new Date());
    client.setQueryData(queryKeys.outfits.generate(date, 0, 0), batch(1));
    for (let n = 1; n <= 5; n += 1) {
      for (const id of [`t${n}`, `b${n}`, `s${n}`]) {
        client.setQueryData(queryKeys.garments.detail(id), detail(id));
      }
    }
    (globalThis.fetch as jest.Mock).mockImplementation(() =>
      Promise.reject(new TypeError('Network request failed')),
    );
    reportUnreachable();
    await renderToday(client);

    expect(await lookOfTheDay()).toBeTruthy();
    expect(
      screen.getByRole('button', { name: 'Me lo pongo' }).props.accessibilityState.disabled,
    ).toBe(true);
    expect(screen.getByText(OFFLINE_NOTE)).toBeTruthy();

    for (let n = 2; n <= 5; n += 1) {
      await fireEvent.press(screen.getByRole('button', { name: 'Otra sugerencia' }));
      await screen.findByText(`Look número ${n} coherente de arriba abajo.`);
    }
    // All five shown and no way to ask for more: explained, button off.
    expect(screen.getByText(/No hay más sugerencias guardadas\./)).toBeTruthy();
    expect(
      screen.getByRole('button', { name: 'Otra sugerencia' }).props.accessibilityState.disabled,
    ).toBe(true);
    expect(calls.filter((call) => call.method !== 'GET')).toHaveLength(0);
  });

  it('shows the last saved batch of an earlier day when today has none', async () => {
    setPlatform('android');
    const client = makeClient();
    client.setQueryData(queryKeys.outfits.generate('2026-09-01', 0, 0), batch(1));
    for (let n = 1; n <= 5; n += 1) {
      for (const id of [`t${n}`, `b${n}`, `s${n}`]) {
        client.setQueryData(queryKeys.garments.detail(id), detail(id));
      }
    }
    (globalThis.fetch as jest.Mock).mockImplementation(() =>
      Promise.reject(new TypeError('Network request failed')),
    );
    reportUnreachable();
    await renderToday(client);

    expect(await lookOfTheDay()).toBeTruthy();
    expect(screen.getByTestId('saved-note')).toBeTruthy();
  });

  it('web ignores the offline state and shows its error instead', async () => {
    setPlatform('web');
    (globalThis.fetch as jest.Mock).mockImplementation(() =>
      Promise.reject(new TypeError('Network request failed')),
    );
    reportUnreachable();
    await renderToday();
    await settle();

    expect(screen.queryByText(OFFLINE_NOTE)).toBeNull();
    expect(await screen.findByText('No pudimos preparar tu look')).toBeTruthy();
  });
});

describe('the daily batch', () => {
  it('is one request per day and wardrobe version, and a wardrobe change asks again', async () => {
    mockApi({ batches: [batch(1), batch(6)] });
    const client = await renderToday();
    await lookOfTheDay();
    expect(
      client.getQueryState(queryKeys.outfits.generate(localDateKey(new Date()), 0, 0))?.status,
    ).toBe('success');

    await act(async () => bumpWardrobeVersion(client));

    expect(await screen.findByText('Look número 6 coherente de arriba abajo.')).toBeTruthy();
    expect(generateBodies).toHaveLength(2);
    // The batch of the old version is dropped once the new one is there.
    await waitFor(() =>
      expect(
        client.getQueryState(queryKeys.outfits.generate(localDateKey(new Date()), 0, 0)),
      ).toBeUndefined(),
    );
  });
});

describe('look-day helpers', () => {
  it('keys the day by local date and stays fresh until the next local midnight', () => {
    const evening = new Date(2026, 9, 4, 23, 30, 0);
    expect(localDateKey(evening)).toBe('2026-10-04');
    expect(msUntilEndOfDay(evening)).toBe(30 * 60 * 1000);
    expect(msUntilEndOfDay(new Date(2026, 9, 4, 0, 0, 0))).toBe(24 * 60 * 60 * 1000);
  });

  it('identifies a look by its garment ids, whatever the order', () => {
    const a = proposalOf(1);
    const b = { ...a, items: [...a.items].reverse() };
    expect(proposalSet(a as never)).toEqual(proposalSet(b as never));
  });
});
