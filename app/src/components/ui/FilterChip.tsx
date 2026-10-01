import { Pressable, StyleSheet, Text } from 'react-native';

import { colors, fontFamilies, radii } from '@/theme';

import { pressFeedback } from './feedback';

type FilterChipProps = {
  label: string;
  /** Number of items behind this filter, shown after the label. */
  count?: number;
  selected: boolean;
  onPress: () => void;
  testID?: string;
};

/** Filter pill with a counter. Selected = filled ink. Border meets 3:1 (WCAG 1.4.11). */
export function FilterChip({ label, count, selected, onPress, testID }: FilterChipProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={count === undefined ? label : `${label}, ${count}`}
      accessibilityState={{ selected }}
      hitSlop={{ top: 2, bottom: 2 }}
      onPress={onPress}
      testID={testID}
      style={(state) => [styles.chip, selected && styles.selected, pressFeedback(state)]}
    >
      <Text style={[styles.label, selected && styles.labelSelected]}>{label}</Text>
      {count === undefined ? null : (
        <Text style={[styles.count, selected && styles.countSelected]}>{count}</Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  chip: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    paddingHorizontal: 15,
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: colors.lineStrong,
    backgroundColor: colors.surface,
  },
  selected: { backgroundColor: colors.ink, borderColor: colors.ink },
  label: { fontFamily: fontFamilies.bodyMedium, fontSize: 13.5, color: colors.ink },
  labelSelected: { color: colors.onInk },
  count: { fontFamily: fontFamilies.bodyMedium, fontSize: 13.5, color: colors.ink3Text },
  countSelected: { color: colors.navInactive },
});
