import { fireEvent, render, screen } from '@testing-library/react-native';

import { ErrorState } from '../src/components/ErrorState';

describe('ErrorState', () => {
  it('calls onRetry when the retry action is pressed (UI-REQ-008)', async () => {
    const onRetry = jest.fn();
    await render(<ErrorState onRetry={onRetry} />);

    fireEvent.press(screen.getByRole('button', { name: 'Reintentar' }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('renders a custom message when provided', async () => {
    await render(<ErrorState message="Fallo de red" onRetry={() => {}} />);

    expect(screen.getByText('Fallo de red')).toBeTruthy();
  });
});
