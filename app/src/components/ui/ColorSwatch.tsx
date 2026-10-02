import { StyleSheet, Text, View } from 'react-native';

import { colors, fontFamilies, radii } from '@/theme';

type ColorSwatchProps = { color: string; label: string };

/** Colour dot plus its name inside a bordered pill. `color` is a hex value. */
export function ColorSwatch({ color, label }: ColorSwatchProps) {
  return (
    <View style={styles.pill}>
      <View style={[styles.dot, { backgroundColor: color }]} />
      <Text style={styles.label}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: 8,
    paddingVertical: 4,
    paddingLeft: 4,
    paddingRight: 12,
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: colors.line,
  },
  dot: { width: 22, height: 22, borderRadius: 11, boxShadow: 'inset 0 0 0 1px rgba(0,0,0,0.08)' },
  label: { fontFamily: fontFamilies.bodyMedium, fontSize: 13, color: colors.ink },
});
