import * as testingLibrary from 'expo-router/testing-library';

describe('tabs layout', () => {
  it('exposes exactly the four required tabs (UI-REQ-002)', async () => {
    // RNTL 14 renders asynchronously; renderRouter returns the render promise.
    await testingLibrary.renderRouter('app', { initialUrl: '/' });

    expect(testingLibrary.screen.getAllByText('Hoy').length).toBeGreaterThan(0);
    expect(testingLibrary.screen.getAllByText('Armario').length).toBeGreaterThan(0);
    // Añadir is a round accent button with no visible label; it is reachable by its accessible name.
    expect(testingLibrary.screen.queryByText('Añadir')).toBeNull();
    expect(testingLibrary.screen.getAllByText('Historial').length).toBeGreaterThan(0);

    // Exactness: every tab button is labelled "<title>, tab, N of <total>",
    // so exactly four of them, all of the form "... of 4", means no extra tab.
    const tabButtons = testingLibrary.screen.getAllByLabelText(/, tab, \d+ of \d+$/);
    expect(tabButtons).toHaveLength(4);
    expect(tabButtons.map((b) => b.props.accessibilityLabel)).toEqual([
      'Hoy, tab, 1 of 4',
      'Armario, tab, 2 of 4',
      'Añadir, tab, 3 of 4',
      'Historial, tab, 4 of 4',
    ]);
  });
});
