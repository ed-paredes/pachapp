import { useEffect, useState } from 'react';
import { StyleSheet, View, type LayoutChangeEvent } from 'react-native';
import Animated, {
  Easing,
  cancelAnimation,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';

import { useReducedMotion } from '@/hooks/useReducedMotion';
import { colors } from '@/theme';

const SCAN_MS = 1800;
/** The line travels between these shares of the thumbnail height (as in the mockup). */
const TOP = 0.12;
const BOTTOM = 0.86;

/**
 * Terracotta line that sweeps over a thumbnail while the photo is being analysed. Under reduced
 * motion it rests in the middle instead of moving. Decorative: hidden from screen readers.
 */
export function ScanLine() {
  const reduced = useReducedMotion();
  const [height, setHeight] = useState(0);
  const progress = useSharedValue(0);

  useEffect(() => {
    if (reduced) {
      cancelAnimation(progress);
      progress.value = 0.5;
      return undefined;
    }
    progress.value = 0;
    progress.value = withRepeat(
      withTiming(1, { duration: SCAN_MS, easing: Easing.inOut(Easing.ease) }),
      -1,
      true,
    );
    return () => cancelAnimation(progress);
  }, [reduced, progress]);

  const style = useAnimatedStyle(() => ({
    transform: [{ translateY: height * (TOP + progress.value * (BOTTOM - TOP)) }],
  }));
  const onLayout = (event: LayoutChangeEvent) => setHeight(event.nativeEvent.layout.height);

  return (
    <View
      pointerEvents="none"
      style={StyleSheet.absoluteFill}
      onLayout={onLayout}
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
    >
      <Animated.View
        style={[styles.line, style]}
        testID={reduced ? 'scan-line-static' : 'scan-line'}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  line: {
    position: 'absolute',
    left: '8%',
    right: '8%',
    top: 0,
    height: 2,
    borderRadius: 1,
    backgroundColor: colors.accent,
    boxShadow: `0px 0px 12px ${colors.accent}`,
  },
});
