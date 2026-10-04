import { cleanup, fireEvent, render, screen } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

import { Segmented } from '@/components/ui/Segmented';

import { withWindowWidths } from './helpers/window';

const options = [
  { value: 'active', label: 'Activas', count: 15 },
  { value: 'laundry', label: 'Lavando', count: 2 },
  { value: 'all', label: 'Todas' },
] as const;

describe('Segmented', () => {
  it('exposes a tab list with the selected option marked', async () => {
    await render(
      <Segmented
        options={[...options]}
        value="laundry"
        onChange={() => undefined}
        accessibilityLabel="Estado"
      />,
    );

    expect(screen.getByLabelText('Estado')).toBeTruthy();
    expect(screen.getAllByRole('tab')).toHaveLength(3);
    const selected = screen.getAllByRole('tab', { selected: true });
    expect(selected).toHaveLength(1);
    expect(selected[0].props.accessibilityLabel).toBe('Lavando, 2');
  });

  it('shows the counters and reports the pressed value', async () => {
    const onChange = jest.fn();
    await render(
      <Segmented
        options={[...options]}
        value="active"
        onChange={onChange}
        accessibilityLabel="Estado"
      />,
    );

    expect(screen.getByText('15')).toBeTruthy();
    await fireEvent.press(screen.getByRole('tab', { name: 'Todas' }));
    expect(onChange).toHaveBeenCalledWith('all');
  });
});

describe('Segmented layout', () => {
  it('keeps every segment at least 44 dp tall and shrinkable to fit a phone', async () => {
    await render(
      <Segmented
        options={[...options]}
        value="active"
        onChange={() => undefined}
        accessibilityLabel="Estado"
      />,
    );

    const style = StyleSheet.flatten(screen.getAllByRole('tab')[0].props.style);
    expect(style.minHeight).toBeGreaterThanOrEqual(44);
    expect(style.flexShrink).toBe(1);
  });

  it('stacks the counter under the label below 480 dp and keeps it inline from 480 dp', async () => {
    const tab = () => StyleSheet.flatten(screen.getAllByRole('tab')[0].props.style);
    await withWindowWidths(800, async (setWidth) => {
      setWidth(479);
      await render(
        <Segmented
          options={[...options]}
          value="active"
          onChange={() => undefined}
          accessibilityLabel="Estado"
        />,
      );
      expect(tab().flexDirection).toBe('column');
      await cleanup();

      setWidth(480);
      await render(
        <Segmented
          options={[...options]}
          value="active"
          onChange={() => undefined}
          accessibilityLabel="Estado"
        />,
      );
      expect(tab().flexDirection).toBe('row');
    });
  });
});
