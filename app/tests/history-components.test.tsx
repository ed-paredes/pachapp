import { cleanup, fireEvent, render, screen } from '@testing-library/react-native';

import { HistoryView } from '@/components/history/HistoryView';
import { KpiCard } from '@/components/history/KpiCard';
import { MonthCalendar, monthTitle } from '@/components/history/MonthCalendar';
import { RankCard } from '@/components/history/RankCard';
import { SafeAreaProvider } from 'react-native-safe-area-context';

const METRICS = {
  frame: { x: 0, y: 0, width: 390, height: 844 },
  insets: { top: 0, left: 0, right: 0, bottom: 0 },
};

afterEach(cleanup);

describe('KpiCard', () => {
  it('shows value and label, and a trend only when given one', async () => {
    await render(<KpiCard value="64%" label="del armario usado" />);
    expect(screen.getByText('64%')).toBeTruthy();
    expect(screen.getByText('del armario usado')).toBeTruthy();
    expect(screen.queryByText(/pts/)).toBeNull();

    await cleanup();
    await render(
      <KpiCard value="5" label="prendas olvidadas" trend={{ text: '+60 días', tone: 'warn' }} />,
    );
    expect(screen.getByText('+60 días')).toBeTruthy();
  });
});

describe('MonthCalendar', () => {
  // September 2026 starts on a Tuesday and has 30 days.
  const month = new Date(2026, 8, 15);

  it('titles the month and lays the days out from Monday', async () => {
    await render(<MonthCalendar month={month} />);

    expect(monthTitle(month)).toBe('Septiembre 2026');
    expect(screen.getByRole('header', { name: 'Septiembre 2026' })).toBeTruthy();
    expect(screen.getByLabelText('1 de septiembre')).toBeTruthy();
    expect(screen.getByLabelText('30 de septiembre')).toBeTruthy();
    expect(screen.queryByLabelText('31 de septiembre')).toBeNull();
    expect(screen.getAllByText(/^[LMXJVSD]$/)).toHaveLength(7);
  });

  it('marks days with an outfit and reports the pressed day', async () => {
    const onSelectDay = jest.fn();
    await render(
      <MonthCalendar
        month={month}
        today={new Date(2026, 8, 1)}
        days={[{ day: 3, color: '#3355AA' }]}
        onSelectDay={onSelectDay}
      />,
    );

    expect(screen.getByLabelText('2 de septiembre')).toBeTruthy();
    await fireEvent.press(screen.getByRole('button', { name: '3 de septiembre, con outfit' }));
    expect(onSelectDay).toHaveBeenCalledWith(3);
    expect(screen.queryByRole('button', { name: '2 de septiembre' })).toBeNull();
  });

  it('wires the month arrows and disables them without handlers', async () => {
    const onPrevious = jest.fn();
    const onNext = jest.fn();
    await render(<MonthCalendar month={month} onPrevious={onPrevious} onNext={onNext} />);
    await fireEvent.press(screen.getByRole('button', { name: 'Mes anterior' }));
    await fireEvent.press(screen.getByRole('button', { name: 'Mes siguiente' }));
    expect(onPrevious).toHaveBeenCalledTimes(1);
    expect(onNext).toHaveBeenCalledTimes(1);

    await cleanup();
    await render(<MonthCalendar month={month} />);
    expect(screen.getByRole('button', { name: 'Mes anterior' })).toBeDisabled();
  });
});

const rows = [
  { id: 'a', name: 'Camiseta azul', detail: '8 usos', color: '#3355AA', thumbUri: null, usage: 1 },
  { id: 'b', name: 'Jersey gris', detail: 'Sin estrenar', color: '#888888', thumbUri: null },
];

describe('RankCard', () => {
  it('draws a bar only for rows with usage and opens the garment', async () => {
    const onOpen = jest.fn();
    await render(<RankCard title="Las que más usas" items={rows} onOpen={onOpen} />);

    expect(screen.getByRole('header', { name: 'Las que más usas' })).toBeTruthy();
    expect(screen.getAllByRole('progressbar')).toHaveLength(1);
    await fireEvent.press(screen.getByRole('button', { name: 'Abrir prenda Jersey gris' }));
    expect(onOpen).toHaveBeenCalledWith('b');
  });

  it('shows the Sugerir action only when a handler is given', async () => {
    const onSuggest = jest.fn();
    await render(<RankCard title="t" items={rows} onOpen={jest.fn()} onSuggest={onSuggest} />);
    await fireEvent.press(screen.getByRole('button', { name: 'Sugerir Jersey gris' }));
    expect(onSuggest).toHaveBeenCalledWith('b');
  });
});

describe('HistoryView', () => {
  const renderView = (props: Partial<React.ComponentProps<typeof HistoryView>>) =>
    render(
      <SafeAreaProvider initialMetrics={METRICS}>
        <HistoryView
          kpis={[]}
          mostWorn={[]}
          secondChance={[]}
          onOpenGarment={jest.fn()}
          {...props}
        />
      </SafeAreaProvider>,
    );

  it('shows the calendar instead of the empty state once it gets one', async () => {
    await renderView({ calendar: { month: new Date(2026, 8, 1) } });
    expect(screen.getByTestId('month-calendar')).toBeTruthy();
    expect(screen.queryByTestId('empty-state')).toBeNull();
  });

  it('puts a retryable notice in the second list slot when it failed to load', async () => {
    const onRetry = jest.fn();
    await renderView({
      mostWorn: [{ id: 'm', name: 'Camisa', detail: '3 usos', color: '#3355AA', thumbUri: null }],
      secondChanceTitle: 'Aún sin estrenar',
      secondChanceError: { onRetry },
    });

    expect(screen.getByTestId('rank-most-worn')).toBeTruthy();
    expect(screen.getByTestId('second-chance-error')).toBeTruthy();
    expect(screen.getByText('Aún sin estrenar')).toBeTruthy();
    expect(screen.queryByTestId('rank-second-chance')).toBeNull();
    await fireEvent.press(screen.getByRole('button', { name: 'Reintentar: Aún sin estrenar' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('shows the notice even when there is nothing else to list, and disables it while retrying', async () => {
    const onRetry = jest.fn();
    await renderView({ secondChanceError: { onRetry, retrying: true } });

    expect(screen.getByTestId('second-chance-error')).toBeTruthy();
    expect(screen.getByRole('button', { name: /^Reintentar/ })).toBeDisabled();
    await fireEvent.press(screen.getByRole('button', { name: /^Reintentar/ }));
    expect(onRetry).not.toHaveBeenCalled();
  });

  it('shows no notice when the second list loaded', async () => {
    await renderView({});
    expect(screen.queryByTestId('second-chance-error')).toBeNull();
  });

  it('renders every KPI it is given', async () => {
    await renderView({
      kpis: [
        { id: 'one', value: '1', label: 'uno' },
        { id: 'two', value: '2', label: 'dos', trend: { text: '↑ 1' } },
      ],
    });
    expect(screen.getByTestId('kpi-one')).toBeTruthy();
    expect(screen.getByText('↑ 1')).toBeTruthy();
  });
});
