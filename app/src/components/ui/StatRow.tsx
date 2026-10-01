import { StyleSheet, Text, View } from 'react-native';

import { colors, fontFamilies, textStyles } from '@/theme';

export type Stat = { value: string; label: string };

type StatRowProps = { stats: Stat[] };

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
          <Text style={styles.value}>{stat.value}</Text>
          <Text style={styles.label}>{stat.label}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row' },
  cell: { flex: 1, gap: 4, paddingVertical: 16, paddingHorizontal: 18 },
  separator: { borderLeftWidth: 1, borderLeftColor: colors.line },
  value: { ...textStyles.stat, color: colors.ink },
  label: { fontFamily: fontFamilies.body, fontSize: 12.5, color: colors.ink2 },
});
