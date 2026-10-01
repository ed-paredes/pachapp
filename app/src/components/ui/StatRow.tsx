import { StyleSheet, Text, View } from 'react-native';

import { colors, fontFamilies, textStyles } from '@/theme';

export type Stat = { value: string; label: string };

type StatRowProps = { stats: Stat[] };

/** Long values ("Hace 12 d") shrink so they stay on one line inside a third of a phone. */
function valueSize(value: string) {
  if (value.length <= 5) return null;
  return value.length <= 7 ? styles.valueMedium : styles.valueSmall;
}

/** Equal columns with hairline separators; the number is set in Fraunces. */
export function StatRow({ stats }: StatRowProps) {
  return (
    <View style={styles.row}>
      {stats.map((stat, index) => (
        <View
          key={stat.label}
          accessible
          accessibilityLabel={`${stat.label}: ${stat.value}`}
          style={[styles.cell, index > 0 && styles.separator]}
        >
          <Text numberOfLines={1} style={[styles.value, valueSize(stat.value)]}>
            {stat.value}
          </Text>
          <Text style={styles.label}>{stat.label}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row' },
  cell: { flex: 1, gap: 4, paddingVertical: 16, paddingHorizontal: 14 },
  separator: { borderLeftWidth: 1, borderLeftColor: colors.line },
  value: { ...textStyles.stat, color: colors.ink },
  valueMedium: { fontSize: 24, lineHeight: 28 },
  valueSmall: { fontSize: 19, lineHeight: 26 },
  label: { fontFamily: fontFamilies.body, fontSize: 12.5, color: colors.ink2 },
});
