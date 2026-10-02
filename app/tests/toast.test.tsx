import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { Pressable, Text } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { TOAST_DURATION_MS, ToastProvider, useToast } from '@/components/ui/Toast';

const metrics = {
  frame: { x: 0, y: 0, width: 390, height: 844 },
  insets: { top: 0, left: 0, right: 0, bottom: 0 },
};

function Trigger() {
  const toast = useToast();
  return (
    <Pressable accessibilityRole="button" onPress={() => toast.show('Guardado')}>
      <Text>Guardar</Text>
    </Pressable>
  );
}

function renderToast() {
  return render(
    <SafeAreaProvider initialMetrics={metrics}>
      <ToastProvider>
        <Trigger />
      </ToastProvider>
    </SafeAreaProvider>,
  );
}

describe('Toast', () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it('shows the message and hides it after about two seconds', async () => {
    await renderToast();
    expect(screen.queryByText('Guardado')).toBeNull();

    await fireEvent.press(screen.getByRole('button', { name: 'Guardar' }));
    expect(screen.getByText('Guardado')).toBeTruthy();

    await act(async () => {
      jest.advanceTimersByTime(TOAST_DURATION_MS - 100);
    });
    expect(screen.getByText('Guardado')).toBeTruthy();

    await act(async () => {
      jest.advanceTimersByTime(200);
    });
    // The text stays mounted while it fades out, but is hidden from assistive tech.
    expect(
      screen.getByTestId('toast', { includeHiddenElements: true }).props
        .accessibilityElementsHidden,
    ).toBe(true);
  });

  it('restarts the timer when the same message is shown again', async () => {
    await renderToast();
    await fireEvent.press(screen.getByRole('button', { name: 'Guardar' }));
    await act(async () => {
      jest.advanceTimersByTime(TOAST_DURATION_MS - 500);
    });
    await fireEvent.press(screen.getByRole('button', { name: 'Guardar' }));
    await act(async () => {
      jest.advanceTimersByTime(TOAST_DURATION_MS - 500);
    });
    // 2 x (duration - 500) has passed since the first press, but only 1.5 s since the second.
    expect(screen.getByTestId('toast').props.accessibilityElementsHidden).toBe(false);
  });

  it('throws a clear error when used outside the provider', async () => {
    const spy = jest.spyOn(console, 'error').mockImplementation(() => undefined);
    await expect(render(<Trigger />)).rejects.toThrow('useToast must be used inside');
    spy.mockRestore();
  });
});
