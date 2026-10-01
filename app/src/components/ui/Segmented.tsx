import { Pressable, StyleSheet, Text, useWindowDimensions, View } from 'react-native';

import { colors, fontFamilies, radii, shadows } from '@/theme';

/** Below this window width the counters stack under the labels. */
const PHONE_WIDTH = 480;

export type SegmentedOption<T extends string> = { value: T; label: string; count?: number };

type SegmentedProps<T extends string> = {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  accessibilityLabel: string;
};

/** Sand track with one white active segment; each option can carry a counter. */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  accessibilityLabel,
}: SegmentedProps<T>) {
  // On phones the counter goes under the label so four segments fit without scrolling.
  const stacked = useWindowDimensions().width < PHONE_WIDTH;
  return (
    <View accessibilityRole="tablist" accessibilityLabel={accessibilityLabel} style={styles.track}>
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <Pressable
            key={option.value}
            accessibilityRole="tab"
            accessibilityLabel={
              option.count === undefined ? option.label : `${option.label}, ${option.count}`
            }
            accessibilityState={{ selected }}
            hitSlop={{ top: 2, bottom: 2 }}
            onPress={() => onChange(option.value)}
            style={[
              styles.segment,
              stacked ? styles.segmentStacked : styles.segmentInline,
              selected && styles.segmentOn,
            ]}
          >
            <Text numberOfLines={1} style={[styles.label, selected && styles.labelOn]}>
              {option.label}
            </Text>
            {option.count === undefined ? null : <Text style={styles.count}>{option.count}</Text>}
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  track: {
    flexDirection: 'row',
    alignSelf: 'flex-start',
    // Never wider than the screen: the segments shrink instead of scrolling.
    maxWidth: '100%',
    padding: 4,
    gap: 2,
    borderRadius: radii.pill,
    backgroundColor: colors.surface2,
  },
  segment: {
    minHeight: 44,
    flexShrink: 1,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radii.pill,
  },
  segmentInline: { flexDirection: 'row', gap: 6, paddingHorizontal: 14 },
  // Label above its counter: four segments fit a 320 dp track without cutting a word.
  segmentStacked: { flexDirection: 'column', paddingVertical: 2, paddingHorizontal: 12 },
  segmentOn: { backgroundColor: colors.surface, boxShadow: shadows.segment },
  label: { fontFamily: fontFamilies.bodyMedium, fontSize: 13, lineHeight: 16, color: colors.ink2 },
  labelOn: { color: colors.ink },
  count: {
    fontFamily: fontFamilies.bodyMedium,
    fontSize: 11.5,
    lineHeight: 14,
    color: colors.ink3Text,
  },
});
