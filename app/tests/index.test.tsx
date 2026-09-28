import { render, screen } from '@testing-library/react-native';

import HomeScreen from '../app/index';

describe('HomeScreen', () => {
  it('renders the Spanish placeholder copy', async () => {
    await render(<HomeScreen />);

    expect(screen.getByText("P'achapp")).toBeTruthy();
    expect(screen.getByText('Armario inteligente — en construcción')).toBeTruthy();
  });
});
