import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';

import SettingsScreen from '../app/settings';

const clients: QueryClient[] = [];

function renderWithClient(ui: ReactNode) {
  // gcTime 0 so no 5-minute garbage-collection timer outlives the test.
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  clients.push(client);
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('SettingsScreen connection status (UI-REQ-014)', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = jest.fn();
  });

  afterEach(async () => {
    await cleanup();
    clients.splice(0).forEach((client) => client.clear());
    globalThis.fetch = originalFetch;
  });

  it('shows the connected line when /health succeeds', async () => {
    (globalThis.fetch as jest.Mock).mockResolvedValueOnce(
      new Response(JSON.stringify({ status: 'ok' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await renderWithClient(<SettingsScreen />);

    await waitFor(() => {
      expect(screen.getByText('Conectado al servidor')).toBeTruthy();
    });
  });

  it('shows an error with retry when /health fails, and recovers on retry', async () => {
    (globalThis.fetch as jest.Mock)
      .mockRejectedValueOnce(new Error('network error'))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: 'ok' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );

    await renderWithClient(<SettingsScreen />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Reintentar' })).toBeTruthy();
    });

    fireEvent.press(screen.getByRole('button', { name: 'Reintentar' }));

    await waitFor(() => {
      expect(screen.getByText('Conectado al servidor')).toBeTruthy();
    });
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });
});
