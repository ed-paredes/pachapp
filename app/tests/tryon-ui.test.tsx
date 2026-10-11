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
import { Image } from 'expo-image';
import { Dimensions, Platform, ScrollView } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { queryKeys } from '../src/api-client/query-keys';
import { TodayView } from '../src/components/today/TodayView';
import type { TodayTryOn } from '../src/components/today/TryOnLayer';
import { TRYON_HELPER, TRYON_MESSAGES } from '../src/components/today/tryon-status';
import type { LookProposal } from '../src/components/today/types';
import { useTodayTryOn } from '../src/hooks/useTodayTryOn';

const proposal: LookProposal = {
  name: 'Tierra relajada',
  pieces: [
    { garmentId: 'g1', role: 'top', name: 'Camiseta marrón', imageUri: 'http://img/g1.png' },
    { garmentId: 'g2', role: 'bottom', name: 'Vaquero negro', imageUri: 'http://img/g2.png' },
    { garmentId: 'g3', role: 'shoes', name: 'Botas', imageUri: 'http://img/g3.png' },
  ],
};

const metrics = {
  frame: { x: 0, y: 0, width: 390, height: 844 },
  insets: { top: 0, left: 0, right: 0, bottom: 0 },
};
const base = {
  dateLabel: 'Jueves, 1 de octubre',
  greeting: 'Buenos días',
  proposal,
  onAddGarment: jest.fn(),
  onOpenWardrobe: jest.fn(),
};

const tryOnProps = (patch: Partial<TodayTryOn> = {}, canvas: Partial<TodayTryOn['canvas']> = {}) =>
  ({
    canTry: true,
    tryOnDisabled: false,
    onTryOn: jest.fn(),
    showToggle: true,
    mode: 'tryon',
    onModeChange: jest.fn(),
    notIncluded: [],
    ...patch,
    canvas: {
      mode: 'tryon',
      status: { phase: 'working', progress: 40, label: 'Vistiendo la parte de abajo…' },
      imageUri: null,
      description: 'Outfit puesto en un modelo: Camiseta marrón',
      onRetry: jest.fn(),
      onShowCollage: jest.fn(),
      ...canvas,
    },
  }) as TodayTryOn;

const renderView = (tryOn?: TodayTryOn) =>
  render(
    <SafeAreaProvider initialMetrics={metrics}>
      <TodayView {...base} onWear={jest.fn()} onShuffle={jest.fn()} tryOn={tryOn} />
    </SafeAreaProvider>,
  );

describe('Hoy try-on view', () => {
  afterEach(async () => {
    await cleanup();
    jest.restoreAllMocks();
  });

  it('shows "Verlo puesto" only when the look can be tried', async () => {
    await renderView(tryOnProps({ showToggle: false }));
    expect(screen.getByRole('button', { name: 'Verlo puesto' })).toBeTruthy();
    expect(screen.queryByRole('tab', { name: 'Puesto' })).toBeNull();
    await cleanup();
    await renderView(tryOnProps({ canTry: false, showToggle: false }));
    expect(screen.queryByRole('button', { name: 'Verlo puesto' })).toBeNull();
    await cleanup();
    await renderView();
    expect(screen.queryByRole('button', { name: 'Verlo puesto' })).toBeNull();
  });

  it('presses the button and disables it when asked', async () => {
    const tryOn = tryOnProps({ showToggle: false });
    await renderView(tryOn);
    await fireEvent.press(screen.getByRole('button', { name: 'Verlo puesto' }));
    expect(tryOn.onTryOn).toHaveBeenCalledTimes(1);
    await cleanup();
    await renderView(tryOnProps({ tryOnDisabled: true }));
    expect(screen.getByRole('button', { name: 'Verlo puesto' })).toBeDisabled();
  });

  it('scrolls to the canvas when "Verlo puesto" is tapped on one column, not on two', async () => {
    const scrollTo = jest.spyOn(ScrollView.prototype, 'scrollTo').mockImplementation(() => {});
    const tryOn = tryOnProps({ showToggle: false });
    const view = await renderView(tryOn);
    await fireEvent.press(screen.getByRole('button', { name: 'Verlo puesto' }));
    expect(tryOn.onTryOn).toHaveBeenCalledTimes(1);
    // The control is not there yet: scrolling now would be undone by the layout shift.
    expect(scrollTo).not.toHaveBeenCalled();
    await view.rerender(
      <SafeAreaProvider initialMetrics={metrics}>
        <TodayView {...base} onWear={jest.fn()} tryOn={{ ...tryOn, showToggle: true }} />
      </SafeAreaProvider>,
    );
    await waitFor(() =>
      expect(scrollTo).toHaveBeenCalledWith(expect.objectContaining({ animated: true })),
    );
    await cleanup();
    scrollTo.mockClear();
    jest
      .spyOn(Dimensions, 'get')
      .mockReturnValue({ width: 1200, height: 800, scale: 1, fontScale: 1 });
    await renderView(tryOn);
    await fireEvent.press(screen.getByRole('button', { name: 'Verlo puesto' }));
    expect(scrollTo).not.toHaveBeenCalled();
  });

  it('does not scroll later on another look when the look changed before the control showed (R3)', async () => {
    const scrollTo = jest.spyOn(ScrollView.prototype, 'scrollTo').mockImplementation(() => {});
    const tryOn = tryOnProps({ showToggle: false });
    const view = await renderView(tryOn);
    await fireEvent.press(screen.getByRole('button', { name: 'Verlo puesto' }));
    // The user shuffles to another look before the control appears there.
    const other: LookProposal = { ...proposal, pieces: proposal.pieces.slice(0, 2) };
    await view.rerender(
      <SafeAreaProvider initialMetrics={metrics}>
        <TodayView {...base} proposal={other} onWear={jest.fn()} tryOn={tryOn} />
      </SafeAreaProvider>,
    );
    await view.rerender(
      <SafeAreaProvider initialMetrics={metrics}>
        <TodayView
          {...base}
          proposal={other}
          onWear={jest.fn()}
          tryOn={{ ...tryOn, showToggle: true }}
        />
      </SafeAreaProvider>,
    );
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });
    expect(scrollTo).not.toHaveBeenCalled();
  });

  it('switches between Collage and Puesto with the segmented control', async () => {
    const tryOn = tryOnProps();
    await renderView(tryOn);
    expect(screen.getByRole('tab', { name: 'Puesto' })).toBeSelected();
    await fireEvent.press(screen.getByRole('tab', { name: 'Collage' }));
    expect(tryOn.onModeChange).toHaveBeenCalledWith('collage');
  });

  it('working: dims the collage and shows the progress, the step and the helper', async () => {
    await renderView(tryOnProps());
    const bar = screen.getByRole('progressbar');
    expect(bar).toHaveProp('accessibilityValue', { min: 0, max: 100, now: 40 });
    expect(screen.getByText('Vistiendo la parte de abajo…')).toBeTruthy();
    expect(screen.getByText(TRYON_HELPER)).toBeTruthy();
    expect(screen.getByTestId('look-collage')).toHaveStyle({ opacity: 0.4 });
  });

  it('working: a queued render sweeps instead of showing an empty bar', async () => {
    await renderView(
      tryOnProps({}, { status: { phase: 'working', progress: 0, label: 'En cola…' } }),
    );
    expect(screen.getByRole('progressbar')).toHaveProp('accessibilityValue', { text: 'En cola…' });
  });

  it('collage mode ignores the try-on', async () => {
    await renderView(tryOnProps({ mode: 'collage' }, { mode: 'collage' }));
    expect(screen.queryByRole('progressbar')).toBeNull();
    expect(screen.getByTestId('look-collage')).not.toHaveStyle({ opacity: 0.4 });
  });

  it('done: shows the image with its description, the tag and the not-included pieces', async () => {
    await renderView(
      tryOnProps(
        { notIncluded: [proposal.pieces[2]] },
        {
          status: { phase: 'done', progress: 100, label: null },
          imageUri: 'http://img/tryon/r1.webp',
        },
      ),
    );
    const image = screen.getByTestId('tryon-image');
    expect(image).toHaveProp('accessibilityLabel', 'Outfit puesto en un modelo: Camiseta marrón');
    expect(image).toHaveProp('contentFit', 'contain');
    // A blurred copy fills the sides of the contained render.
    expect(screen.getByTestId('tryon-backdrop', { includeHiddenElements: true })).toHaveProp(
      'contentFit',
      'cover',
    );
    expect(screen.getByTestId('tryon-backdrop', { includeHiddenElements: true })).toHaveProp(
      'blurRadius',
      30,
    );
    expect(screen.getByText('Imagen generada · aproximación')).toBeTruthy();
    expect(screen.getByText('No incluidos en la imagen')).toBeTruthy();
    expect(within(screen.getByTestId('tryon-not-included')).getByLabelText('Botas')).toBeTruthy();
    expect(screen.queryByTestId('look-collage')).toBeNull();
  });

  it('done: omits the not-included row when nothing was left out', async () => {
    await renderView(
      tryOnProps(
        {},
        { status: { phase: 'done', progress: 100, label: null }, imageUri: 'http://i' },
      ),
    );
    expect(screen.queryByText('No incluidos en la imagen')).toBeNull();
  });

  it.each([
    ['retry', true],
    ['later', false],
    ['final', false],
  ] as const)('error (%s): retry button is %s, "Ver collage" always', async (errorKind, retry) => {
    const canvas = {
      status: {
        phase: 'error' as const,
        progress: null,
        label: null,
        errorKind,
        message: TRYON_MESSAGES.retry,
      },
    };
    const tryOn = tryOnProps({}, canvas);
    await renderView(tryOn);
    expect(screen.getByText(TRYON_MESSAGES.retry)).toBeTruthy();
    expect(!!screen.queryByRole('button', { name: 'Reintentar' })).toBe(retry);
    if (retry) {
      await fireEvent.press(screen.getByRole('button', { name: 'Reintentar' }));
      expect(tryOn.canvas.onRetry).toHaveBeenCalled();
    }
    await fireEvent.press(screen.getByRole('button', { name: 'Ver collage' }));
    expect(tryOn.canvas.onShowCollage).toHaveBeenCalled();
  });
});

describe('useTodayTryOn on Hoy', () => {
  const originalFetch = globalThis.fetch;
  const caps = { enabled: true, supported_categories: ['top', 'bottom'], max_passes: 3 };
  const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  const renderRow = (patch: Record<string, unknown> = {}) => ({
    id: 'r1',
    status: 'pending',
    step: null,
    progress: 0,
    error: null,
    img: null,
    garment_ids: ['g1', 'g2', 'g3'],
    skipped_garment_ids: [],
    unsupported_garment_ids: ['g3'],
    created_at: '2026-10-09T10:00:00Z',
    ...patch,
  });
  const realOS = Platform.OS;
  let client: QueryClient;

  function Probe({ offline = false, id = 'a' }: { offline?: boolean; id?: string }) {
    const pieces = id === 'a' ? proposal.pieces : proposal.pieces.slice(0, 2).reverse().slice(0, 1);
    const tryOn = useTodayTryOn(pieces, offline);
    return (
      <SafeAreaProvider initialMetrics={metrics}>
        <TodayView {...base} proposal={{ ...proposal, pieces }} tryOn={tryOn} onWear={jest.fn()} />
      </SafeAreaProvider>
    );
  }
  const mount = (props: { offline?: boolean; id?: string } = {}) =>
    render(
      <QueryClientProvider client={client}>
        <Probe {...props} />
      </QueryClientProvider>,
    );

  beforeEach(() => {
    Object.defineProperty(Platform, 'OS', { configurable: true, get: () => 'android' });
    globalThis.fetch = jest
      .fn()
      .mockImplementation(async (req: Request) =>
        req.url.includes('/tryon/capabilities') ? json(caps) : json(renderRow(), 202),
      );
    jest.spyOn(Image, 'prefetch').mockResolvedValue(true);
    jest.spyOn(Image, 'getCachePathAsync').mockResolvedValue(null);
    client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: Infinity } },
    });
  });
  afterEach(async () => {
    await cleanup();
    client.clear();
    globalThis.fetch = originalFetch;
    Object.defineProperty(Platform, 'OS', { configurable: true, get: () => realOS });
    jest.restoreAllMocks();
  });

  const postCalls = () =>
    (globalThis.fetch as jest.Mock).mock.calls.filter(
      ([req]) => (req as Request).method === 'POST',
    );

  it('hides the button when try-on is disabled', async () => {
    (globalThis.fetch as jest.Mock).mockImplementation(async () =>
      json({ ...caps, enabled: false }),
    );
    await mount();
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: 'Verlo puesto' })).toBeNull();
  });

  it('tapping the button posts the look and opens Puesto with the progress', async () => {
    await mount();
    const button = await screen.findByRole('button', { name: 'Verlo puesto' });
    expect(screen.queryByRole('tab', { name: 'Puesto' })).toBeNull();
    await fireEvent.press(button);
    await waitFor(() => expect(screen.getByRole('tab', { name: 'Puesto' })).toBeSelected());
    expect(screen.getByRole('progressbar')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Verlo puesto' })).toBeDisabled();
    expect(postCalls()).toHaveLength(1);
    await fireEvent.press(screen.getByRole('tab', { name: 'Collage' }));
    expect(screen.queryByRole('progressbar')).toBeNull();
  });

  it('with a finished render the button only switches to Puesto, and a new look starts in Collage', async () => {
    client.setQueryData(queryKeys.tryon.capabilities, caps);
    client.setQueryData(queryKeys.tryon.byLook('g1,g2,g3'), { renderId: 'r1' });
    client.setQueryData(
      queryKeys.tryon.detail('r1'),
      renderRow({ status: 'done', progress: 100, img: 'tryon/r1.webp' }),
    );
    const view = await mount();
    // A look with a finished render opens on Puesto.
    expect(await screen.findByTestId('tryon-image')).toBeTruthy();
    expect(within(screen.getByTestId('tryon-not-included')).getByLabelText('Botas')).toBeTruthy();
    await fireEvent.press(screen.getByRole('tab', { name: 'Collage' }));
    expect(screen.queryByTestId('tryon-image')).toBeNull();
    await fireEvent.press(screen.getByRole('button', { name: 'Verlo puesto' }));
    expect(screen.getByTestId('tryon-image')).toBeTruthy();
    expect(postCalls()).toHaveLength(0);

    // Another look has no render: no control, plain collage.
    await act(async () => {
      view.rerender(
        <QueryClientProvider client={client}>
          <Probe id="b" />
        </QueryClientProvider>,
      );
    });
    expect(screen.queryByRole('tab', { name: 'Puesto' })).toBeNull();
    expect(screen.queryByTestId('tryon-image')).toBeNull();
  });

  it.each([
    ['blank_output', false],
    ['invalid_params', false],
    ['garment_missing', true],
    ['engine_error', true],
  ])('after a failed render (%s) the button is enabled: %s', async (error, enabled) => {
    client.setQueryData(queryKeys.tryon.capabilities, caps);
    client.setQueryData(queryKeys.tryon.byLook('g1,g2,g3'), { renderId: 'r1' });
    client.setQueryData(queryKeys.tryon.detail('r1'), renderRow({ status: 'failed', error }));
    await mount();
    const button = await screen.findByRole('button', { name: 'Verlo puesto' });
    if (enabled) expect(button).toBeEnabled();
    else expect(button).toBeDisabled();
  });

  it('offline: the button is off without a saved render and works with one', async () => {
    client.setQueryData(queryKeys.tryon.capabilities, caps);
    await mount({ offline: true });
    expect(await screen.findByRole('button', { name: 'Verlo puesto' })).toBeDisabled();
    await cleanup();

    client.setQueryData(queryKeys.tryon.byLook('g1,g2,g3'), { renderId: 'r1' });
    client.setQueryData(
      queryKeys.tryon.detail('r1'),
      renderRow({ status: 'done', progress: 100, img: 'tryon/r1.webp' }),
    );
    await mount({ offline: true });
    expect(await screen.findByRole('button', { name: 'Verlo puesto' })).toBeEnabled();
    expect(screen.getByTestId('tryon-image')).toBeTruthy();
  });
});
