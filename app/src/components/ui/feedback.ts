import { Platform, type PressableStateCallbackType, type ViewStyle } from 'react-native';

/** Pressable state as react-native-web reports it: `hovered` exists on web only. */
export type PressState = PressableStateCallbackType & { hovered?: boolean };

/**
 * Press feedback shared by the redesign controls: a small lift on hover (web only) and a
 * slight shrink while pressed (touch and web). Spread into a `Pressable` style callback.
 */
export function pressFeedback({ hovered, pressed }: PressState): ViewStyle {
  if (pressed) return { transform: [{ scale: 0.98 }] };
  if (Platform.OS === 'web' && hovered) return { transform: [{ translateY: -2 }] };
  return {};
}
