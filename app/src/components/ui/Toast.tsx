import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';

import { useReducedMotion } from '@/hooks/useReducedMotion';
import { colors, fontFamilies, radii, shadows } from '@/theme';

import { useTabBarTop } from './tab-bar-metrics';

/** How long a toast stays on screen. */
export const TOAST_DURATION_MS = 2200;
const FADE_MS = 250;
/** Space between the toast and the tab bar below it. */
const TOAST_GAP = 12;

type ToastApi = { show: (message: string) => void };

const ToastContext = createContext<ToastApi | null>(null);

/** Shows short confirmations ("Guardado") from anywhere in the tree. */
export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error('useToast must be used inside <ToastProvider>');
  return api;
}

/** Mounts the toast layer: a dark pill above the tab bar that disappears after ~2 s. */
export function ToastProvider({ children }: { children: ReactNode }) {
  // `text` survives the fade-out; `serial` restarts the timer when the same message repeats.
  const [toast, setToast] = useState({ text: '', visible: false, serial: 0 });
  const show = useCallback((text: string) => {
    setToast((prev) => ({ text, visible: true, serial: prev.serial + 1 }));
  }, []);
  const api = useMemo(() => ({ show }), [show]);

  useEffect(() => {
    if (!toast.visible) return undefined;
    const timer = setTimeout(
      () => setToast((prev) => ({ ...prev, visible: false })),
      TOAST_DURATION_MS,
    );
    return () => clearTimeout(timer);
  }, [toast.visible, toast.serial]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <ToastLayer text={toast.text} visible={toast.visible} />
    </ToastContext.Provider>
  );
}

function ToastLayer({ text, visible }: { text: string; visible: boolean }) {
  const bottom = useTabBarTop() + TOAST_GAP;
  const reduced = useReducedMotion();
  const progress = useSharedValue(0);

  useEffect(() => {
    const target = visible ? 1 : 0;
    progress.value = reduced ? target : withTiming(target, { duration: FADE_MS });
  }, [visible, reduced, progress]);

  const animated = useAnimatedStyle(() => ({
    opacity: progress.value,
    transform: [{ translateY: reduced ? 0 : (1 - progress.value) * 16 }],
  }));

  return (
    <View pointerEvents="none" style={[styles.layer, { bottom }]}>
      <Animated.View
        accessibilityElementsHidden={!visible}
        importantForAccessibility={visible ? 'yes' : 'no-hide-descendants'}
        accessibilityLiveRegion="polite"
        accessibilityRole="alert"
        style={[styles.toast, animated]}
        testID="toast"
      >
        {text ? <Text style={styles.text}>{text}</Text> : null}
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  layer: { position: 'absolute', left: 0, right: 0, alignItems: 'center' },
  toast: {
    paddingVertical: 12,
    paddingHorizontal: 18,
    borderRadius: radii.pill,
    backgroundColor: colors.ink,
    boxShadow: shadows.raised,
  },
  text: { fontFamily: fontFamilies.bodyMedium, fontSize: 14, color: colors.onInk },
});
