import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';

/**
 * Minimal per-device key/value storage abstraction for purely local UI
 * preferences that have no server-side equivalent (e.g. "capture tips seen",
 * UI-REQ-020).
 *
 * - Web uses `localStorage` directly, as specified by 07-app-ui.md.
 * - Native (iOS/Android) uses `@react-native-async-storage/async-storage`,
 *   the standard Expo-recommended persistent key/value store
 *   (https://docs.expo.dev/versions/latest/sdk/async-storage/), installed
 *   via `npx expo install`. `expo-secure-store` was not used because this
 *   value isn't a secret — it's a non-sensitive UI flag — and AsyncStorage
 *   is the lighter-weight, conventional choice for that case.
 */
export async function getItem(key: string): Promise<string | null> {
  if (Platform.OS === 'web') {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  }
  return AsyncStorage.getItem(key);
}

export async function setItem(key: string, value: string): Promise<void> {
  if (Platform.OS === 'web') {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      /* ignore quota/availability errors on web */
    }
    return;
  }
  await AsyncStorage.setItem(key, value);
}
