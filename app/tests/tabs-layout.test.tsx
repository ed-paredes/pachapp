import * as testingLibrary from 'expo-router/testing-library';

describe('tabs layout', () => {
  it('exposes exactly the four required tabs (UI-REQ-002)', async () => {
    // RNTL 14 renders asynchronously; renderRouter returns the render promise.
    await testingLibrary.renderRouter('app', { initialUrl: '/' });

    expect(testingLibrary.screen.getAllByText('Hoy').length).toBeGreaterThan(0);
    expect(testingLibrary.screen.getAllByText('Armario').length).toBeGreaterThan(0);
    expect(testingLibrary.screen.getAllByText('Añadir').length).toBeGreaterThan(0);
    expect(testingLibrary.screen.getAllByText('Historial').length).toBeGreaterThan(0);
  });
});
