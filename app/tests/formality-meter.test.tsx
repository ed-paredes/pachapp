import { render, screen } from '@testing-library/react-native';

import { FormalityMeter } from '@/components/ui/FormalityMeter';

describe('FormalityMeter', () => {
  it.each([
    [1, 'Muy informal'],
    [3, 'Smart casual'],
    [5, 'Formal'],
  ])('level %i reads "%s"', async (level, label) => {
    await render(<FormalityMeter level={level} />);

    expect(screen.getByText(label)).toBeTruthy();
    const meter = screen.getByRole('progressbar');
    expect(meter.props.accessibilityLabel).toBe(`Formalidad: ${label}, ${level} de 5`);
    expect(meter.props.accessibilityValue).toEqual({ min: 1, max: 5, now: level, text: label });
  });

  it('clamps out-of-range levels', async () => {
    await render(<FormalityMeter level={9} />);
    expect(screen.getByText('Formal')).toBeTruthy();
  });

  it('clamps levels below the range to the first step', async () => {
    await render(<FormalityMeter level={-4} />);
    expect(screen.getByText('Muy informal')).toBeTruthy();
  });

  it.each([[NaN], [Infinity], [null], [undefined]])(
    'renders nothing for level %s',
    async (level) => {
      await render(<FormalityMeter level={level} />);
      expect(screen.queryByRole('progressbar')).toBeNull();
      expect(screen.toJSON()).toBeNull();
    },
  );
});
