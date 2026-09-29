import { render, screen } from '@testing-library/react-native';

import TodayScreen from '../app/(tabs)/index';

describe('TodayScreen (Hoy)', () => {
  it('renders the empty-state copy from UI-REQ-005', async () => {
    await render(<TodayScreen />);

    expect(
      screen.getByText('Aún no tienes suficientes prendas para generar un outfit'),
    ).toBeTruthy();
  });
});
