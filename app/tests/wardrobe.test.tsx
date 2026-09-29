import { render, screen } from '@testing-library/react-native';

import WardrobeScreen from '../app/(tabs)/wardrobe';

describe('WardrobeScreen (Armario)', () => {
  it('renders the empty-state copy inviting to Añadir (UI-REQ-004)', async () => {
    await render(<WardrobeScreen />);

    expect(screen.getByText('Tu armario está vacío')).toBeTruthy();
  });
});
