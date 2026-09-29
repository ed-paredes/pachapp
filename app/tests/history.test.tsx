import { render, screen } from '@testing-library/react-native';

import HistoryScreen from '../app/(tabs)/history';

describe('HistoryScreen (Historial)', () => {
  it('renders the exact empty-state copy from UI-REQ-007', async () => {
    await render(<HistoryScreen />);

    expect(screen.getByText('Todavía no has registrado ningún outfit')).toBeTruthy();
  });
});
