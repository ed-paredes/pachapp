import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, fontFamilies, radii, shadows } from '@/theme';

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
            style={[styles.segment, selected && styles.segmentOn]}
          >
            <Text style={[styles.label, selected && styles.labelOn]}>{option.label}</Text>
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
    padding: 4,
    borderRadius: radii.pill,
    backgroundColor: colors.surface2,
  },
  segment: {
    minHeight: 40,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 14,
    borderRadius: radii.pill,
  },
  segmentOn: { backgroundColor: colors.surface, boxShadow: shadows.segment },
  label: { fontFamily: fontFamilies.bodyMedium, fontSize: 13, color: colors.ink2 },
  labelOn: { color: colors.ink },
  count: { fontFamily: fontFamilies.bodyMedium, fontSize: 11.5, color: colors.ink3Text },
});
