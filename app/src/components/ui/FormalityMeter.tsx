import { StyleSheet, Text, View } from 'react-native';

import { colors, fontFamilies } from '@/theme';

export const FORMALITY_LABELS = [
  'Muy informal',
  'Informal',
  'Smart casual',
  'Arreglado',
  'Formal',
] as const;

type FormalityMeterProps = {
  /** 1 (Muy informal) to 5 (Formal); values outside are clamped, a missing or NaN level renders nothing. */
  level: number | null | undefined;
};

/** Five-segment meter plus its label. */
export function FormalityMeter({ level }: FormalityMeterProps) {
  if (level == null || !Number.isFinite(level)) return null;
  const filled = Math.min(5, Math.max(1, Math.round(level)));
  const label = FORMALITY_LABELS[filled - 1];
  return (
    <View
      accessible
      accessibilityRole="progressbar"
      accessibilityLabel={`Formalidad: ${label}, ${filled} de 5`}
      accessibilityValue={{ min: 1, max: 5, now: filled, text: label }}
      style={styles.row}
    >
      {[1, 2, 3, 4, 5].map((n) => (
        <View key={n} style={[styles.segment, n <= filled && styles.segmentOn]} />
      ))}
      <Text style={styles.label}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  segment: { width: 26, height: 6, borderRadius: 3, backgroundColor: colors.surface3 },
  segmentOn: { backgroundColor: colors.ink },
  label: { marginLeft: 8, fontFamily: fontFamilies.body, fontSize: 12.5, color: colors.ink2 },
});
