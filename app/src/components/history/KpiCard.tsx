import { StyleSheet, Text } from 'react-native';

import { Card } from '@/components/ui';
import { colors, fontFamilies, textStyles } from '@/theme';

export type KpiTrend = {
  /** "↑ 4 vs. septiembre". */
  text: string;
  tone?: 'good' | 'warn';
};

type KpiCardProps = {
  /** Big number: "64%", "5". */
  value: string;
  /** What it counts: "del armario usado". */
  label: string;
  /**
   * Small line under the label. The API keeps no history to compare against yet, so screens leave
   * it out; it is here for when it does.
   */
  trend?: KpiTrend;
  testID?: string;
};

/** Statistic card: the number in Fraunces, its label and an optional trend line. */
export function KpiCard({ value, label, trend, testID }: KpiCardProps) {
  return (
    <Card style={styles.card} testID={testID}>
      <Text style={styles.value}>{value}</Text>
      <Text style={styles.label}>{label}</Text>
      {trend ? (
        <Text style={[styles.trend, trend.tone === 'warn' && styles.trendWarn]}>{trend.text}</Text>
      ) : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  card: { flexGrow: 1, flexBasis: 150, padding: 18, gap: 4 },
  value: { ...textStyles.stat, fontSize: 34, lineHeight: 38, color: colors.ink },
  label: { fontFamily: fontFamilies.body, fontSize: 13, lineHeight: 18, color: colors.ink2 },
  trend: {
    marginTop: 6,
    fontFamily: fontFamilies.bodySemiBold,
    fontSize: 12,
    color: colors.okText,
  },
  trendWarn: { color: colors.warnText },
});
