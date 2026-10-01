import { fireEvent, render, screen } from '@testing-library/react-native';

import { AltLooksList, type AltLook } from '@/components/today/AltLookCard';
import { LookCanvas, pieceBySlot } from '@/components/today/LookCanvas';
import { LookWhyCard } from '@/components/today/LookWhyCard';
import { TipCard } from '@/components/today/TipCard';
import type { LookPiece, LookReason } from '@/components/today/types';
import { WeatherPill } from '@/components/today/WeatherPill';

const piece = (garmentId: string, role: LookPiece['role'], overrides: Partial<LookPiece> = {}) => ({
  garmentId,
  role,
  name: `Prenda ${garmentId}`,
  imageUri: `http://img/${garmentId}.png`,
  color: '#8B5E3C',
  ...overrides,
});

const PIECES: LookPiece[] = [
  piece('a', 'outerwear'),
  piece('b', 'top'),
  piece('c', 'bottom'),
  piece('d', 'shoes'),
];

const REASONS: LookReason[] = [
  {
    icon: { ios: 'sparkles', android: 'auto_awesome', web: 'auto_awesome' },
    title: 'Estrenas algo.',
    text: 'La camiseta marrón todavía no la has usado.',
  },
];

describe('pieceBySlot', () => {
  it('maps roles to collage slots and prefers outerwear and top over mid-layer and one-piece', () => {
    const result = pieceBySlot([
      piece('m', 'mid_layer'),
      piece('o', 'outerwear'),
      piece('v', 'one_piece'),
      piece('t', 'top'),
      piece('s', 'shoes'),
      piece('x', 'accessory'),
    ]);
    expect(result.layer?.garmentId).toBe('o');
    expect(result.top?.garmentId).toBe('t');
    expect(result.shoes?.garmentId).toBe('s');
    expect(result.bottom).toBeUndefined();
  });

  it('skips pieces without an image', () => {
    expect(pieceBySlot([piece('a', 'top', { imageUri: null })]).top).toBeUndefined();
  });
});

describe('LookCanvas', () => {
  it('draws every piece as a labelled image', async () => {
    await render(<LookCanvas pieces={PIECES} />);
    for (const id of ['a', 'b', 'c', 'd']) {
      expect(screen.getByTestId(`look-piece-${id}`)).toBeTruthy();
    }
  });

  it('shows the formality tag and the match badge only when given', async () => {
    const view = await render(<LookCanvas pieces={PIECES} />);
    expect(screen.queryByTestId('look-match')).toBeNull();
    expect(screen.queryByText(/Formalidad/)).toBeNull();

    await view.rerender(
      <LookCanvas pieces={PIECES} formalityLabel="Casual · Formalidad 2/5" matchPercent={94} />,
    );
    expect(screen.getByText('Casual · Formalidad 2/5')).toBeTruthy();
    expect(screen.getByText('94% match')).toBeTruthy();
  });
});

describe('LookWhyCard', () => {
  it('renders name, reasons and pieces, and opens a piece', async () => {
    const onOpenPiece = jest.fn();
    await render(
      <LookWhyCard
        name="Tierra relajada"
        reasons={REASONS}
        pieces={PIECES}
        onOpenPiece={onOpenPiece}
      />,
    );

    expect(screen.getByText('Look del día')).toBeTruthy();
    expect(screen.getByText('Tierra relajada')).toBeTruthy();
    expect(screen.getByText('Estrenas algo.')).toBeTruthy();

    await fireEvent.press(screen.getByRole('button', { name: 'Abrir prenda Prenda b' }));
    expect(onOpenPiece).toHaveBeenCalledWith('b');
  });

  it('hides the name, the reasons and the buttons when their props are absent', async () => {
    await render(<LookWhyCard pieces={PIECES} />);

    expect(screen.queryByRole('header')).toBeNull();
    expect(screen.queryByText('Estrenas algo.')).toBeNull();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('wires "Me lo pongo" and the icon-only "Otra sugerencia"', async () => {
    const onWear = jest.fn();
    const onShuffle = jest.fn();
    await render(<LookWhyCard pieces={PIECES} onWear={onWear} onShuffle={onShuffle} />);

    await fireEvent.press(screen.getByRole('button', { name: 'Me lo pongo' }));
    await fireEvent.press(screen.getByRole('button', { name: 'Otra sugerencia' }));
    expect(onWear).toHaveBeenCalledTimes(1);
    expect(onShuffle).toHaveBeenCalledTimes(1);
  });
});

describe('AltLooksList', () => {
  const looks: AltLook[] = [
    { id: 'l1', name: 'Smart de jueves', pieces: PIECES, matchPercent: 89 },
    { id: 'l2', name: 'Fresco y simple', pieces: PIECES.slice(0, 2) },
  ];

  it('renders nothing without looks', async () => {
    await render(<AltLooksList looks={[]} />);
    expect(screen.queryByText('Otras opciones para hoy')).toBeNull();
  });

  it('summarises each look and reports the chosen one', async () => {
    const onSelect = jest.fn();
    await render(<AltLooksList looks={looks} onSelect={onSelect} />);

    expect(screen.getByText('4 prendas · 89% match')).toBeTruthy();
    expect(screen.getByText('2 prendas')).toBeTruthy();
    await fireEvent.press(screen.getByRole('button', { name: 'Ver look Fresco y simple' }));
    expect(onSelect).toHaveBeenCalledWith('l2');
  });
});

describe('WeatherPill', () => {
  it('renders nothing without data', async () => {
    await render(<WeatherPill />);
    expect(screen.queryByTestId('weather-pill')).toBeNull();
  });

  it('shows temperature, summary and maximum', async () => {
    await render(<WeatherPill weather={{ temperature: 18, summary: 'Nublado', max: 21 }} />);
    expect(screen.getByText('Nublado, máx. 21°', { exact: false })).toBeTruthy();
  });
});

describe('TipCard', () => {
  const icon = { ios: 'drop', android: 'water_drop', web: 'water_drop' } as const;

  it('is a plain card without onPress', async () => {
    await render(<TipCard icon={icon} tone="info" title="2 prendas en el cesto" text="Vaquero." />);
    expect(screen.getByText('2 prendas en el cesto')).toBeTruthy();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('is one button that reports presses when it goes somewhere', async () => {
    const onPress = jest.fn();
    await render(
      <TipCard
        icon={icon}
        tone="accent"
        title="Has usado el 64 % de tu armario"
        onPress={onPress}
      />,
    );
    await fireEvent.press(screen.getByRole('button', { name: 'Has usado el 64 % de tu armario' }));
    expect(onPress).toHaveBeenCalledTimes(1);
  });
});
