import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { getItem, setItem } from '../src/lib/device-storage';

jest.mock('../src/lib/device-storage', () => ({
  getItem: jest.fn(),
  setItem: jest.fn(),
}));

const mockGetItem = getItem as jest.Mock;
const mockSetItem = setItem as jest.Mock;

const metrics = {
  frame: { x: 0, y: 0, width: 390, height: 844 },
  insets: { top: 0, left: 0, right: 0, bottom: 0 },
};

// eslint-disable-next-line @typescript-eslint/no-require-imports
const AddScreen = require('../app/(tabs)/add').default;

function renderScreen() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { gcTime: 0 } },
  });
  return render(
    <SafeAreaProvider initialMetrics={metrics}>
      <QueryClientProvider client={client}>
        <AddScreen />
      </QueryClientProvider>
    </SafeAreaProvider>,
  );
}

describe('AddScreen capture tips panel (UI-REQ-020 / UI-SCN-007)', () => {
  beforeEach(() => {
    mockGetItem.mockReset();
    mockSetItem.mockReset();
  });

  it('shows the panel automatically the first time, and remembers dismissal', async () => {
    mockGetItem.mockResolvedValue(null);
    mockSetItem.mockResolvedValue(undefined);

    await renderScreen();

    await waitFor(() => {
      expect(screen.getByTestId('capture-tips-panel')).toBeTruthy();
    });

    await fireEvent.press(screen.getByRole('button', { name: 'Entendido, cerrar consejos' }));

    expect(screen.queryByTestId('capture-tips-panel')).toBeNull();
    // It rests as the compact Consejo card.
    expect(screen.getByTestId('capture-tip-card')).toBeTruthy();
    expect(mockSetItem).toHaveBeenCalledWith('pachapp.captureTips.seen', 'true');

    // Re-opens via the help icon on the screen.
    await fireEvent.press(screen.getByRole('button', { name: 'Ver consejos de captura' }));

    expect(screen.getByTestId('capture-tips-panel')).toBeTruthy();
  });

  it('does not auto-show the panel again once it was already seen', async () => {
    mockGetItem.mockResolvedValue('true');

    await renderScreen();

    await waitFor(() => {
      expect(mockGetItem).toHaveBeenCalledWith('pachapp.captureTips.seen');
    });

    // Flush the resolved getItem promise so the hook has processed 'true'.
    await act(async () => {
      await mockGetItem.mock.results[0].value;
    });

    expect(screen.queryByTestId('capture-tips-panel')).toBeNull();
  });
});
