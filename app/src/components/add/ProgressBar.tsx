import { LinearGradient } from 'expo-linear-gradient';
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

/** Terracotta gradient of the mockup's progress bar. */
export const PROGRESS_GRADIENT = ['#B5562F', '#D9895F'] as const;
/** Width of the sweeping segment of an indeterminate bar, as a share of the track. */
const SWEEP_SHARE = 0.4;
const SWEEP_MS = 1300;

type ProgressBarProps = {
  /** 0-100 when the progress is known; `null` while it is not (indeterminate sweep). */
  value: number | null;
  /** Accessible name; the state is announced next to it. */
  label: string;
  testID?: string;
};

/**
 * Thin progress track with the terracotta gradient. Determinate when `value` is a number (the
 * real job progress); otherwise a segment sweeps along the track, or rests still when the user
 * asked for reduced motion.
 */
export function ProgressBar({ value, label, testID }: ProgressBarProps) {
  const determinate = value !== null;
  const clamped = determinate ? Math.max(0, Math.min(100, value)) : 0;
  return (
    <View
      accessible
      accessibilityRole="progressbar"
      accessibilityLabel={label}
      accessibilityValue={determinate ? { min: 0, max: 100, now: clamped } : { text: label }}
      style={styles.track}
      testID={testID}
    >
      {determinate ? <Fill percent={clamped} /> : <Sweep />}
    </View>
  );
}

function Fill({ percent }: { percent: number }) {
  const reduced = useReducedMotion();
  const width = useSharedValue(percent);
  useEffect(() => {
    width.value = reduced ? percent : withTiming(percent, { duration: 400 });
  }, [percent, reduced, width]);
  const style = useAnimatedStyle(() => ({ width: `${width.value}%` }));
  return (
    <Animated.View style={[styles.fill, style]} testID="progress-fill">
      <Gradient />
    </Animated.View>
  );
}

function Sweep() {
  const reduced = useReducedMotion();
  const [trackWidth, setTrackWidth] = useState(0);
  const progress = useSharedValue(0);
  const segment = trackWidth * SWEEP_SHARE;

  useEffect(() => {
    if (reduced) {
      cancelAnimation(progress);
      progress.value = 0.5;
      return undefined;
    }
    progress.value = 0;
    progress.value = withRepeat(
      withTiming(1, { duration: SWEEP_MS, easing: Easing.inOut(Easing.ease) }),
      -1,
      false,
    );
    return () => cancelAnimation(progress);
  }, [reduced, progress]);

  const style = useAnimatedStyle(() => ({
    transform: [{ translateX: -segment + progress.value * (trackWidth + segment) }],
  }));
  const onLayout = (event: LayoutChangeEvent) => setTrackWidth(event.nativeEvent.layout.width);

  return (
    <View style={styles.sweepHost} onLayout={onLayout}>
      <Animated.View
        style={[styles.fill, { width: `${SWEEP_SHARE * 100}%` }, style]}
        testID={reduced ? 'progress-sweep-static' : 'progress-sweep'}
      >
        <Gradient />
      </Animated.View>
    </View>
  );
}

function Gradient() {
  return (
    <LinearGradient
      colors={PROGRESS_GRADIENT}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 0 }}
      style={StyleSheet.absoluteFill}
    />
  );
}

const styles = StyleSheet.create({
  track: { height: 6, borderRadius: 3, backgroundColor: colors.surface2, overflow: 'hidden' },
  fill: { height: 6, borderRadius: 3, overflow: 'hidden' },
  sweepHost: { height: 6, width: '100%' },
});
