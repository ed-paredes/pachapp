import { Pressable, StyleSheet, Text } from 'react-native';

import { colors, fontFamilies, radii } from '@/theme';

import { pressFeedback } from './feedback';

type AddChipProps = {
  /** Visible text; defaults to "+ Añadir". */
  label?: string;
  /** What the chip adds, for screen readers (e.g. "Añadir marca"). */
  accessibilityLabel?: string;
  onPress: () => void;
};

/** Dashed chip that stands in for an empty field instead of "Sin definir". */
export function AddChip({ label = '+ Añadir', accessibilityLabel, onPress }: AddChipProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      hitSlop={{ top: 4, bottom: 4 }}
      onPress={onPress}
      style={(state) => [styles.chip, pressFeedback(state)]}
    >
      <Text style={styles.label}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  chip: {
    minHeight: 36,
    alignSelf: 'flex-start',
    justifyContent: 'center',
    paddingHorizontal: 12,
    borderRadius: radii.pill,
    borderWidth: 1.5,
    borderStyle: 'dashed',
    borderColor: colors.lineStrong,
  },
  label: { fontFamily: fontFamilies.bodyMedium, fontSize: 13, color: colors.ink3Text },
});
