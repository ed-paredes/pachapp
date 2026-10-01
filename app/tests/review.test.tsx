import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react-native';

import { buildColors } from '../src/lib/palette';
import { CATEGORY_LABELS } from '../src/lib/labels';

const mockReplace = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ replace: mockReplace, push: jest.fn() }),
  useLocalSearchParams: () => ({ id: 'g1' }),
}));

// eslint-disable-next-line @typescript-eslint/no-require-imports
const ReviewScreen = require('../app/review/[id]').default;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

const entry = (name: string, hex: string, proportion: number) => ({
  name,
  hex,
  lab: [10, 0, 0] as [number, number, number],
  proportion,
});

let garment: Record<string, unknown>;
const baseGarment = (): Record<string, unknown> => ({
  id: 'g1',
  category: 'top',
  subcategory: 'camiseta',
  colors: [entry('negro', '#19191c', 0.7), entry('blanco', '#f5f5f3', 0.3)],
  is_neutral: true,
  pattern: 'solid',
  status: 'active',
  needs_review: true,
  user_verified: false,
  img_thumb: 'thumb/g1.webp',
  img_cutout: 'cutout/g1.png',
  img_original: 'original/g1.jpg',
  wear_count: 0,
  last_worn_at: null,
  created_at: '2026-09-30T10:00:00Z',
  updated_at: '2026-09-30T10:00:00Z',
  job: null,
  color_confidence: 0.9,
  ai_confidence: {
    category: { value: 'top', confidence: 0.4, source: 'zero_shot' },
    formality: { value: 2, confidence: 0.9, source: 'zero_shot' },
  },
  formality: 2,
  style_tags: ['casual'],
  seasons: ['summer'],
  warmth: 1,
  material: 'algodón',
  brand: null,
  notes: null,
  outfit_count: 0,
});

const settings = {
  needs_review_threshold: 0.7,
  color_review_threshold: 0.7,
};

type Call = { method: string; path: string; body: unknown };
let calls: Call[];
let patchStatus: number;

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
  if (request.method === 'GET' && url.pathname === '/settings') return json(settings);
  if (request.method === 'GET' && url.pathname === '/garments/g1') return json(garment);
  if (request.method === 'PATCH' && url.pathname === '/garments/g1') {
    if (patchStatus !== 200) {
      return json({ error: { code: 'X', message: 'boom', details: null } }, patchStatus);
    }
    garment = { ...garment, ...(body as object) };
    return json(garment);
  }
  if (request.method === 'POST' && url.pathname === '/garments/g1/review/complete') {
    garment = { ...garment, needs_review: false, user_verified: true };
    return json(garment);
  }
  return json({ error: { code: 'NOT_FOUND', message: 'no', details: null } }, 404);
}

async function renderScreen() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ReviewScreen />
    </QueryClientProvider>,
  );
}

/** Expands a collapsed summary row ("Formalidad, 2 de 5"). */
const openRow = (label: string) => fireEvent.press(screen.getByLabelText(new RegExp(`^${label},`)));

const patches = () => calls.filter((c) => c.method === 'PATCH');

describe('ReviewScreen (Revisión)', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    garment = baseGarment();
    calls = [];
    patchStatus = 200;
    mockReplace.mockClear();
    globalThis.fetch = jest.fn((input: Request) => handle(input)) as unknown as typeof fetch;
  });

  afterEach(async () => {
    await cleanup();
    globalThis.fetch = originalFetch;
  });

  it('shows the cutout and highlights only the doubtful fields', async () => {
    await renderScreen();
    expect(await screen.findByTestId('review-image')).toBeTruthy();
    expect(screen.getByTestId('highlight-category')).toBeTruthy();
    expect(screen.queryByTestId('highlight-formality')).toBeNull();
    expect(screen.queryByTestId('highlight-colors')).toBeNull();
    expect(screen.getByTestId('review-badge')).toBeTruthy();
  });

  it('highlights empty attributes while pending review and low colour confidence', async () => {
    garment = { ...baseGarment(), ai_confidence: null, pattern: null, color_confidence: 0.3 };
    await renderScreen();
    await screen.findByTestId('review-image');
    expect(screen.getByTestId('highlight-pattern')).toBeTruthy();
    expect(screen.getByTestId('highlight-colors')).toBeTruthy();
    expect(screen.queryByTestId('highlight-category')).toBeNull();
  });

  it('keeps the highlight and the screen after editing another chip (UI-SCN-003)', async () => {
    await renderScreen();
    await screen.findByTestId('review-image');

    await openRow('Formalidad');
    await fireEvent.press(screen.getByLabelText('Formalidad: 4'));
    await waitFor(() => expect(patches()).toHaveLength(1));
    expect(patches()[0].body).toEqual({ formality: 4 });
    // The row collapses after a successful save and shows the new value.
    await waitFor(() => expect(screen.queryByLabelText('Formalidad: 4')).toBeNull());
    expect(screen.getByLabelText('Formalidad, 4 de 5')).toBeTruthy();

    expect(screen.getByTestId('highlight-category')).toBeTruthy();
    expect(screen.getByTestId('review-badge')).toBeTruthy();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it('keeps the highlight on the edited field itself until "Revisión terminada"', async () => {
    await renderScreen();
    await screen.findByTestId('review-image');
    await fireEvent.press(screen.getByLabelText(`Categoría: ${CATEGORY_LABELS.shoes}`));
    await waitFor(() => expect(patches()).toHaveLength(1));
    expect(patches()[0].body).toEqual({ category: 'shoes' });
    await waitFor(() =>
      expect(
        screen.getByLabelText(`Categoría: ${CATEGORY_LABELS.shoes}`).props.accessibilityState
          .selected,
      ).toBe(true),
    );
    expect(screen.getByTestId('highlight-category')).toBeTruthy();
  });

  it('sends multi-select edits and caps style tags at 3', async () => {
    garment = { ...baseGarment(), style_tags: ['casual', 'classic', 'street'] };
    await renderScreen();
    await screen.findByTestId('review-image');
    await openRow('Estilos');
    expect(screen.getByLabelText('Estilo: Minimal').props.accessibilityState.disabled).toBe(true);

    await fireEvent.press(screen.getByLabelText('Estilo: Classic'.replace('Classic', 'Clásico')));
    await waitFor(() => expect(patches()).toHaveLength(1));
    expect(patches()[0].body).toEqual({ style_tags: ['casual', 'street'] });

    await openRow('Temporadas');
    expect(screen.queryByLabelText('Estilo: Clásico')).toBeNull();
    await fireEvent.press(screen.getByLabelText('Temporada: Invierno'));
    await waitFor(() => expect(patches()).toHaveLength(2));
    expect(patches()[1].body).toEqual({ seasons: ['summer', 'winter'] });
  });

  it('saves free text on submit', async () => {
    await renderScreen();
    await screen.findByTestId('review-image');
    await openRow('Material');
    const input = screen.getByLabelText('Material');
    await fireEvent.changeText(input, 'lana merino');
    await fireEvent(input, 'submitEditing');
    await waitFor(() => expect(patches()).toHaveLength(1));
    expect(patches()[0].body).toEqual({ material: 'lana merino' });
  });

  it('saves pending text before "Revisión terminada" completes the review', async () => {
    await renderScreen();
    await screen.findByTestId('review-image');
    await openRow('Material');
    await fireEvent.changeText(screen.getByLabelText('Material'), 'lana merino');
    // No blur or submit: the footer button is tapped while the field is still focused.
    await fireEvent.press(screen.getByLabelText('Revisión terminada'));
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/(tabs)/wardrobe'));
    expect(patches()).toHaveLength(1);
    expect(patches()[0].body).toEqual({ material: 'lana merino' });
    const order = calls.map((c) => c.method);
    expect(order.indexOf('PATCH')).toBeLessThan(order.indexOf('POST'));
  });

  it('saves pending text when another row is opened', async () => {
    await renderScreen();
    await screen.findByTestId('review-image');
    await openRow('Material');
    await fireEvent.changeText(screen.getByLabelText('Material'), 'lana merino');
    await openRow('Formalidad');
    await waitFor(() => expect(patches()).toHaveLength(1));
    expect(patches()[0].body).toEqual({ material: 'lana merino' });
  });

  it('does not save unchanged text when finishing', async () => {
    await renderScreen();
    await screen.findByTestId('review-image');
    await openRow('Material');
    await fireEvent.press(screen.getByLabelText('Revisión terminada'));
    await waitFor(() => expect(mockReplace).toHaveBeenCalled());
    expect(patches()).toHaveLength(0);
  });

  it('does not complete the review when saving pending text fails', async () => {
    patchStatus = 500;
    await renderScreen();
    await screen.findByTestId('review-image');
    await openRow('Material');
    await fireEvent.changeText(screen.getByLabelText('Material'), 'lana merino');
    await fireEvent.press(screen.getByLabelText('Revisión terminada'));
    expect(await screen.findByTestId('error-material')).toBeTruthy();
    expect(mockReplace).not.toHaveBeenCalled();
    expect(
      calls.filter((c) => c.method === 'POST' && c.path === '/garments/g1/review/complete'),
    ).toHaveLength(0);
  });

  it('edits colours with a valid PATCH body (descending proportions, sum <= 1)', async () => {
    await renderScreen();
    await screen.findByTestId('review-image');
    await openRow('Colores');
    await fireEvent.press(screen.getByLabelText('Cambiar colores'));
    await fireEvent.press(screen.getByLabelText('Color: rojo'));
    await waitFor(() => expect(patches()).toHaveLength(1));

    const sent = (patches()[0].body as { colors: { name: string; proportion: number }[] }).colors;
    expect(sent.map((c) => c.name)).toEqual(['negro', 'blanco', 'rojo']);
    const proportions = sent.map((c) => c.proportion);
    expect([...proportions].sort((a, b) => b - a)).toEqual(proportions);
    expect(proportions.reduce((a, b) => a + b, 0)).toBeLessThanOrEqual(1);
    expect(sent[0]).toEqual(expect.objectContaining({ hex: '#19191c', proportion: 0.6363 }));
  });

  it('does not allow removing the last colour', async () => {
    garment = { ...baseGarment(), colors: [entry('negro', '#19191c', 1)] };
    await renderScreen();
    await screen.findByTestId('review-image');
    await openRow('Colores');
    await fireEvent.press(screen.getByLabelText('Cambiar colores'));
    expect(screen.getByLabelText('Color: negro').props.accessibilityState.disabled).toBe(true);
  });

  it('reverts the value and shows an inline message when the PATCH fails', async () => {
    patchStatus = 500;
    await renderScreen();
    await screen.findByTestId('review-image');
    await openRow('Formalidad');
    await fireEvent.press(screen.getByLabelText('Formalidad: 5'));
    expect(await screen.findByTestId('error-formality')).toBeTruthy();
    expect(screen.getByLabelText('Formalidad: 2').props.accessibilityState.selected).toBe(true);
    expect(screen.getByLabelText('Formalidad: 5').props.accessibilityState.selected).toBe(false);
  });

  it('"Revisión terminada" completes the review and goes back to Armario', async () => {
    await renderScreen();
    await screen.findByTestId('review-image');
    await fireEvent.press(screen.getByLabelText('Revisión terminada'));
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/(tabs)/wardrobe'));
    expect(
      calls.filter((c) => c.method === 'POST' && c.path === '/garments/g1/review/complete'),
    ).toHaveLength(1);
  });

  it('lists doubtful fields expanded and collapses the rest into summary rows', async () => {
    await renderScreen();
    await screen.findByTestId('review-image');
    expect(screen.getByText('Por revisar')).toBeTruthy();
    // Doubtful field: editor visible, no summary row.
    expect(screen.getByLabelText(`Categoría: ${CATEGORY_LABELS.top}`)).toBeTruthy();
    expect(screen.queryByLabelText(/^Categoría,/)).toBeNull();
    // Other fields: one-line summaries, no editors.
    expect(screen.getByLabelText('Formalidad, 2 de 5')).toBeTruthy();
    expect(screen.getByLabelText('Colores, negro, blanco')).toBeTruthy();
    expect(screen.queryByLabelText('Formalidad: 3')).toBeNull();
    expect(screen.queryByLabelText('Color: rojo')).toBeNull();
  });

  it('expands one row at a time and collapses it again on tap', async () => {
    await renderScreen();
    await screen.findByTestId('review-image');
    await openRow('Formalidad');
    expect(screen.getByLabelText('Formalidad: 3')).toBeTruthy();
    await openRow('Abrigo');
    expect(screen.queryByLabelText('Formalidad: 3')).toBeNull();
    expect(screen.getByLabelText('Abrigo: 3')).toBeTruthy();
    await openRow('Abrigo');
    expect(screen.queryByLabelText('Abrigo: 3')).toBeNull();
  });

  it('keeps multi-select rows open after a save and keeps the highlight', async () => {
    await renderScreen();
    await screen.findByTestId('review-image');
    await openRow('Temporadas');
    await fireEvent.press(screen.getByLabelText('Temporada: Invierno'));
    await waitFor(() => expect(patches()).toHaveLength(1));
    expect(screen.getByLabelText('Temporada: Verano')).toBeTruthy();
    expect(screen.getByTestId('highlight-category')).toBeTruthy();
  });

  it('shows colour swatches with percentages and the palette only after "Cambiar colores"', async () => {
    garment = { ...baseGarment(), color_confidence: 0.3 };
    await renderScreen();
    await screen.findByTestId('review-image');
    expect(screen.getByTestId('highlight-colors')).toBeTruthy();
    expect(screen.getByText('negro 70 %')).toBeTruthy();
    expect(screen.getByText('blanco 30 %')).toBeTruthy();
    expect(screen.queryByLabelText('Color: rojo')).toBeNull();
    await fireEvent.press(screen.getByLabelText('Cambiar colores'));
    expect(screen.getByLabelText('Color: rojo')).toBeTruthy();
    await fireEvent.press(screen.getByLabelText('Listo con los colores'));
    expect(screen.queryByLabelText('Color: rojo')).toBeNull();
  });

  it('keeps "Revisión terminada" outside the scrolling content and shows a failure inline', async () => {
    await renderScreen();
    await screen.findByTestId('review-image');
    expect(
      within(screen.getByTestId('review-scroll')).queryByLabelText('Revisión terminada'),
    ).toBeNull();
    globalThis.fetch = jest.fn(() =>
      Promise.resolve(json({ error: { code: 'X', message: 'boom', details: null } }, 500)),
    ) as unknown as typeof fetch;
    await fireEvent.press(screen.getByLabelText('Revisión terminada'));
    expect(await screen.findByTestId('complete-error')).toBeTruthy();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it('shows loading, then an error with retry, and a 404 state', async () => {
    let fail = true;
    globalThis.fetch = jest.fn((input: Request) =>
      fail && new URL(input.url).pathname === '/garments/g1'
        ? Promise.resolve(
            json({ error: { code: 'E', message: 'Sin conexión', details: null } }, 500),
          )
        : handle(input),
    ) as unknown as typeof fetch;
    await renderScreen();
    expect(screen.getByTestId('loading-state-spinner')).toBeTruthy();
    expect(await screen.findByTestId('error-state')).toBeTruthy();
    fail = false;
    await fireEvent.press(screen.getByLabelText('Reintentar'));
    expect(await screen.findByTestId('review-image')).toBeTruthy();
  });

  it('shows a not-found message on 404', async () => {
    globalThis.fetch = jest.fn(() =>
      Promise.resolve(
        json({ error: { code: 'GARMENT_NOT_FOUND', message: 'x', details: null } }, 404),
      ),
    ) as unknown as typeof fetch;
    await renderScreen();
    expect(await screen.findByText('No encontramos esta prenda')).toBeTruthy();
  });
});

describe('buildColors', () => {
  const previous = [entry('negro', '#19191c', 0.6), entry('blanco', '#f5f5f3', 0.4)];

  it('keeps proportions of kept names and splits the rest evenly', () => {
    const built = buildColors(
      ['negro', 'blanco', 'rojo', 'verde'],
      [entry('negro', '#19191c', 0.5), entry('blanco', '#f5f5f3', 0.3)],
    );
    const total = built.reduce((sum, c) => sum + c.proportion, 0);
    expect(total).toBeLessThanOrEqual(1);
    expect(built.map((c) => c.name)).toEqual(['negro', 'blanco', 'rojo', 'verde']);
    expect(built[2].proportion).toBe(built[3].proportion);
  });

  it('renormalises after a removal and sorts descending', () => {
    const built = buildColors(['blanco'], previous);
    expect(built).toHaveLength(1);
    expect(built[0].proportion).toBe(1);
    const two = buildColors(['rojo', 'negro'], previous);
    expect(two.map((c) => c.name)).toEqual(['negro', 'rojo']);
    const proportions = two.map((c) => c.proportion);
    expect([...proportions].sort((a, b) => b - a)).toEqual(proportions);
  });

  it('fills hex and Lab from the palette', () => {
    const [white] = buildColors(['blanco'], null);
    expect(white.hex).toBe('#f5f5f3');
    expect(white.lab[0]).toBeGreaterThan(95);
  });
});
