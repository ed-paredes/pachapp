import { Pressable, StyleSheet, Text } from 'react-native';

type ChipProps = {
  group: string;
  label: string;
  selected: boolean;
  onPress: () => void;
  disabled?: boolean;
};

/** Selectable pill used by the attribute editors of Revisión. */
export function Chip({ group, label, selected, onPress, disabled }: ChipProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${group}: ${label}`}
      accessibilityState={{ selected, disabled: !!disabled }}
      disabled={disabled}
      onPress={onPress}
      style={[styles.chip, selected && styles.chipSelected]}
    >
      <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  chip: {
    paddingVertical: 6,
    paddingHorizontal: 14,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#D0D5DD',
  },
  chipSelected: { backgroundColor: '#208AEF', borderColor: '#208AEF' },
  chipText: { fontSize: 13, fontWeight: '500' },
  chipTextSelected: { color: '#fff' },
});
