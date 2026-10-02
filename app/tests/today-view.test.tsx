import { fireEvent, render, screen } from '@testing-library/react-native';

import { SafeAreaProvider } from 'react-native-safe-area-context';

import { TodayView } from '@/components/today/TodayView';
import type { LookProposal } from '@/components/today/types';

const proposal: LookProposal = {
  name: 'Tierra relajada',
  formalityLabel: 'Casual · Formalidad 2/5',
  matchPercent: 94,
  reasons: [
    {
      icon: { ios: 'sparkles', android: 'auto_awesome', web: 'auto_awesome' },
      title: 'Estrenas algo.',
      text: 'La camiseta todavía no la has usado.',
    },
  ],
  pieces: [
    {
      garmentId: 'b',
      role: 'top',
      name: 'Camiseta marrón',
      imageUri: 'http://img/b.png',
      color: '#8B5E3C',
    },
    {
      garmentId: 'c',
      role: 'bottom',
      name: 'Vaquero negro',
      imageUri: 'http://img/c.png',
      color: '#222222',
    },
  ],
};

const metrics = {
  frame: { x: 0, y: 0, width: 390, height: 844 },
  insets: { top: 0, left: 0, right: 0, bottom: 0 },
};
const renderView = (ui: React.ReactElement) =>
  render(<SafeAreaProvider initialMetrics={metrics}>{ui}</SafeAreaProvider>);

const base = {
  dateLabel: 'Jueves, 1 de octubre',
  greeting: 'Buenos días',
  onAddGarment: jest.fn(),
};

describe('TodayView', () => {
  it('shows the empty state and the date without a proposal', async () => {
    await renderView(<TodayView {...base} />);

    expect(screen.getByText('Jueves, 1 de octubre')).toBeTruthy();
    expect(screen.getByTestId('empty-state')).toBeTruthy();
    expect(screen.queryByText('Look del día')).toBeNull();
  });

  it('shows the look, the reasons and the actions once a proposal exists', async () => {
    const onWear = jest.fn();
    const onOpenPiece = jest.fn();
    await renderView(
      <TodayView
        {...base}
        proposal={proposal}
        weather={{ temperature: 18, summary: 'Nublado', max: 21 }}
        onWear={onWear}
        onOpenPiece={onOpenPiece}
      />,
    );

    expect(screen.queryByTestId('empty-state')).toBeNull();
    expect(screen.getByRole('header', { name: 'Buenos días. Hoy te proponemos…' })).toBeTruthy();
    expect(screen.getByTestId('weather-pill')).toBeTruthy();
    expect(screen.getByText('Tierra relajada')).toBeTruthy();
    expect(screen.getByText('94% match')).toBeTruthy();
    expect(screen.getByText('Estrenas algo.')).toBeTruthy();

    await fireEvent.press(screen.getByRole('button', { name: 'Me lo pongo' }));
    await fireEvent.press(screen.getByRole('button', { name: 'Abrir prenda Vaquero negro' }));
    expect(onWear).toHaveBeenCalledTimes(1);
    expect(onOpenPiece).toHaveBeenCalledWith('c');
  });

  it('renders only the notices it receives', async () => {
    await renderView(
      <TodayView {...base} usageTip={{ title: 'Has usado el 64% de tu armario' }} />,
    );

    expect(screen.getByText('Has usado el 64% de tu armario')).toBeTruthy();
    expect(screen.queryByTestId('tip-laundry')).toBeNull();
  });
});
