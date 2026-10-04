import { Dimensions } from 'react-native';

/**
 * Runs `fn` with `Dimensions.get` spied, and restores the real implementation afterwards
 * (even when `fn` throws). `setWidth(w)` switches the reported window to `w` dp wide; call it
 * before rendering, and `cleanup()` between widths. Responsive layouts here read the window
 * through `Dimensions.get`, so this is how a test exercises a breakpoint boundary.
 */
export async function withWindowWidths(
  height: number,
  fn: (setWidth: (width: number) => void) => Promise<void> | void,
): Promise<void> {
  const spy = jest.spyOn(Dimensions, 'get');
  try {
    await fn((width) => {
      spy.mockReturnValue({ width, height, scale: 2, fontScale: 1 });
    });
  } finally {
    spy.mockRestore();
  }
}
