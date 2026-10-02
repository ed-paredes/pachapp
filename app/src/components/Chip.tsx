import { Pressable, StyleSheet, Text } from 'react-native';

import { colors, fontFamilies, fontSizes, radii } from '@/theme';

type ChipProps = {
  group: string;
  label: string;
  selected: boolean;
  onPress: () => void;
  disabled?: boolean;
};

/** Selectable pill used by the Armario filters and the attribute editors of Revisión. */
export function Chip({ group, label, selected, onPress, disabled }: ChipProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${group}: ${label}`}
      accessibilityState={{ selected, disabled: !!disabled }}
      disabled={disabled}
      hitSlop={4}
      onPress={onPress}
      style={[styles.chip, selected && styles.chipSelected, disabled && styles.chipDisabled]}
    >
      <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  chip: {
    minHeight: 36,
    justifyContent: 'center',
    paddingHorizontal: 14,
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: colors.hairline,
    backgroundColor: colors.plinth,
  },
  chipSelected: { backgroundColor: colors.olive, borderColor: colors.olive },
  chipDisabled: { opacity: 0.5 },
  chipText: {
    fontFamily: fontFamilies.bodyMedium,
    fontSize: fontSizes.small,
    color: colors.charcoal,
  },
  chipTextSelected: { color: colors.onOlive },
});
