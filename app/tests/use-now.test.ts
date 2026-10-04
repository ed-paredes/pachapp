import { act, renderHook } from '@testing-library/react-native';
import { AppState, type AppStateStatus } from 'react-native';

import { nextTick, useNow } from '@/hooks/useNow';

describe('nextTick', () => {
  it('returns the next greeting boundary, then midnight', async () => {
    expect(nextTick(new Date(2026, 9, 3, 3, 0)).getHours()).toBe(6);
    expect(nextTick(new Date(2026, 9, 3, 6, 0)).getHours()).toBe(12);
    expect(nextTick(new Date(2026, 9, 3, 13, 0)).getHours()).toBe(20);
    expect(nextTick(new Date(2026, 9, 3, 21, 0))).toEqual(new Date(2026, 9, 4, 0, 0));
    expect(nextTick(new Date(2026, 9, 31, 23, 59))).toEqual(new Date(2026, 10, 1, 0, 0));
  });
});

describe('useNow', () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => {
    jest.restoreAllMocks();
    jest.useRealTimers();
  });

  it('moves to the next day after local midnight', async () => {
    jest.setSystemTime(new Date(2026, 9, 3, 23, 59, 0));
    const { result } = await renderHook(() => useNow());
    expect(result.current.getDate()).toBe(3);

    await act(async () => {
      jest.advanceTimersByTime(2 * 60 * 1000);
    });
    expect(result.current.getDate()).toBe(4);
    expect(result.current.getMonth()).toBe(9);
  });

  it('updates at a greeting boundary', async () => {
    jest.setSystemTime(new Date(2026, 9, 3, 11, 59, 0));
    const { result } = await renderHook(() => useNow());
    expect(result.current.getHours()).toBe(11);

    await act(async () => {
      jest.advanceTimersByTime(2 * 60 * 1000);
    });
    expect(result.current.getHours()).toBe(12);
  });

  it('refreshes when the app returns to the foreground', async () => {
    let listener: (state: AppStateStatus) => void = () => undefined;
    const remove = jest.fn();
    jest.spyOn(AppState, 'addEventListener').mockImplementation((_type, handler) => {
      listener = handler;
      return { remove };
    });
    jest.setSystemTime(new Date(2026, 9, 3, 22, 0, 0));
    const clear = jest.spyOn(globalThis, 'clearTimeout');
    const { result, unmount } = await renderHook(() => useNow());
    expect(result.current.getDate()).toBe(3);

    // The device slept through midnight: no timer fired, so only the foreground event can fix it.
    jest.setSystemTime(new Date(2026, 9, 4, 8, 0, 0));
    await act(async () => listener('background'));
    expect(result.current.getDate()).toBe(3);
    await act(async () => listener('active'));
    expect(result.current.getDate()).toBe(4);
    expect(result.current.getHours()).toBe(8);

    await unmount();
    expect(remove).toHaveBeenCalled();
    expect(clear).toHaveBeenCalled();
  });
});
