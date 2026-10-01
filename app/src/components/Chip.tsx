import { Pressable, StyleSheet, Text } from 'react-native';

import { pressFeedback } from '@/components/ui/feedback';
import { colors, fontFamilies, radii } from '@/theme';

type ChipProps = {
  group: string;
  label: string;
  selected: boolean;
  onPress: () => void;
  disabled?: boolean;
  /** Grows to share the row with its siblings (level pickers). */
  grow?: boolean;
};

/** Selectable 44 dp pill for the attribute editors of Revisión. Selected = filled ink. */
export function Chip({ group, label, selected, onPress, disabled, grow }: ChipProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${group}: ${label}`}
      accessibilityState={{ selected, disabled: !!disabled }}
      disabled={disabled}
      hitSlop={{ top: 2, bottom: 2 }}
      onPress={onPress}
      style={(state) => [
        styles.chip,
        grow && styles.grow,
        selected && styles.chipSelected,
        disabled && styles.chipDisabled,
        pressFeedback(state),
      ]}
    >
      <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  chip: {
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 16,
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: colors.lineStrong,
    backgroundColor: colors.surface,
  },
  grow: { flex: 1, paddingHorizontal: 0 },
  chipSelected: { backgroundColor: colors.ink, borderColor: colors.ink },
  chipDisabled: { opacity: 0.45 },
  chipText: { fontFamily: fontFamilies.bodyMedium, fontSize: 14, color: colors.ink },
  chipTextSelected: { color: colors.onInk },
});
