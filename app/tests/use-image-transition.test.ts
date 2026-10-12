import { act, renderHook, waitFor } from '@testing-library/react-native';
import { AccessibilityInfo } from 'react-native';

import { useImageTransition } from '../src/hooks/useImageTransition';

describe('useImageTransition', () => {
  let listener: ((value: boolean) => void) | undefined;
  const remove = jest.fn();
  let subscriptions = 0;

  function mockReduceMotion(initial: boolean) {
    jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(initial);
    jest.spyOn(AccessibilityInfo, 'addEventListener').mockImplementation(((
      event: string,
      handler: (value: boolean) => void,
    ) => {
      if (event === 'reduceMotionChanged') {
        listener = handler;
        subscriptions += 1;
      }
      return { remove };
    }) as never);
  }

  beforeEach(() => {
    remove.mockClear();
    subscriptions = 0;
    listener = undefined;
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('fades by default', async () => {
    mockReduceMotion(false);
    const { result } = await renderHook(() => useImageTransition());
    await waitFor(() => expect(listener).toBeDefined());
    expect(result.current).toBe(160);
  });

  it('does not animate when the OS already asks for reduced motion', async () => {
    mockReduceMotion(true);
    const { result } = await renderHook(() => useImageTransition());
    await waitFor(() => expect(result.current).toBe(0));
  });

  it('follows reduce-motion changes while mounted and unsubscribes on unmount', async () => {
    mockReduceMotion(false);
    const { result, unmount } = await renderHook(() => useImageTransition());
    await waitFor(() => expect(listener).toBeDefined());

    await act(async () => listener?.(true));
    expect(result.current).toBe(0);
    await act(async () => listener?.(false));
    expect(result.current).toBe(160);

    await unmount();
    expect(subscriptions).toBe(1);
    expect(remove).toHaveBeenCalledTimes(1);
  });
});
