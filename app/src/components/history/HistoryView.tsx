import { StyleSheet, Text, useWindowDimensions, View } from 'react-native';

import { IconSymbol } from '@/components/IconSymbol';
import { SectionError } from '@/components/SectionError';
import { Eyebrow, Screen, Title } from '@/components/ui';
import { colors, fontFamilies, radii, shadows, spacing, TWO_COLUMNS } from '@/theme';

import { KpiCard, type KpiTrend } from './KpiCard';
import { MonthCalendar } from './MonthCalendar';
import { RankCard, type RankItem } from './RankCard';

const CALENDAR_ICON = {
  ios: 'calendar',
  android: 'calendar_month',
  web: 'calendar_month',
} as const;

export type HistoryKpi = { id: string; value: string; label: string; trend?: KpiTrend };

type HistoryViewProps = {
  /** Only the statistics the API can compute; empty = no row. */
  kpis: HistoryKpi[];
  /**
   * Props of `MonthCalendar`. Undefined until a wear-log endpoint exists: the empty state shows
   * instead of a calendar with invented days.
   */
  calendar?: React.ComponentProps<typeof MonthCalendar>;
  /** "Las que más usas"; the card is hidden when empty. */
  mostWorn: RankItem[];
  /** "Dales otra oportunidad"; the card is hidden when empty. */
  secondChance: RankItem[];
  /** Title of the second list; "Dales otra oportunidad" only makes sense with real history. */
  secondChanceTitle?: string;
  /**
   * The data behind the second list failed to load. A retryable notice takes the card's place, so
   * a failed load is not mistaken for "nothing to show"; the rest of the screen is unchanged.
   */
  secondChanceError?: { onRetry: () => void; retrying?: boolean };
  onOpenGarment: (id: string) => void;
  /** Adds the "Sugerir" button to the second list (needs the outfit engine). */
  onSuggest?: (id: string) => void;
};

/**
 * Historial: use statistics, the month calendar and two rankings. Everything the API cannot
 * provide yet (calendar, trends) arrives through optional props and is absent without data.
 */
export function HistoryView({
  kpis,
  calendar,
  mostWorn,
  secondChance,
  secondChanceTitle = 'Dales otra oportunidad',
  secondChanceError,
  onOpenGarment,
  onSuggest,
}: HistoryViewProps) {
  const { width } = useWindowDimensions();
  const wide = width >= TWO_COLUMNS;
  const lists = mostWorn.length > 0 || secondChance.length > 0 || secondChanceError !== undefined;

  return (
    <Screen testID="history-screen">
      <View style={styles.page}>
        <View style={styles.header}>
          <Eyebrow>Tu uso</Eyebrow>
          <Title>Historial</Title>
        </View>

        {kpis.length > 0 ? (
          <View style={styles.kpis} testID="history-kpis">
            {kpis.map(({ id, ...kpi }) => (
              <KpiCard key={id} testID={`kpi-${id}`} {...kpi} />
            ))}
          </View>
        ) : null}

        {calendar ? (
          <MonthCalendar {...calendar} />
        ) : (
          <View style={[styles.empty, !wide && styles.emptyStacked]} testID="empty-state">
            <View style={styles.emptyIcon}>
              <IconSymbol name={CALENDAR_ICON} size={26} color={colors.accentText} />
            </View>
            <View style={styles.emptyText}>
              <Text accessibilityRole="header" style={styles.emptyTitle}>
                Todavía no has registrado ningún outfit
              </Text>
              <Text style={styles.emptyBody}>
                Cuando lo hagas, aquí verás qué te pusiste cada día del mes.
              </Text>
            </View>
          </View>
        )}

        {lists ? (
          <View style={[styles.lists, wide && styles.listsWide]}>
            {mostWorn.length > 0 ? (
              <RankCard
                title="Las que más usas"
                items={mostWorn}
                onOpen={onOpenGarment}
                testID="rank-most-worn"
              />
            ) : null}
            {secondChanceError ? (
              <SectionError
                title={secondChanceTitle}
                onRetry={secondChanceError.onRetry}
                retrying={secondChanceError.retrying}
                testID="second-chance-error"
              />
            ) : secondChance.length > 0 ? (
              <RankCard
                title={secondChanceTitle}
                items={secondChance}
                onOpen={onOpenGarment}
                onSuggest={onSuggest}
                testID="rank-second-chance"
              />
            ) : null}
          </View>
        ) : null}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  page: { gap: spacing.lg, paddingTop: spacing.md },
  header: { gap: 10, marginBottom: spacing.xs },
  kpis: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md },
  lists: { gap: spacing.md },
  listsWide: { flexDirection: 'row', alignItems: 'flex-start' },
  empty: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
    padding: 24,
    borderRadius: radii.lg,
    backgroundColor: colors.surface,
    boxShadow: shadows.card,
  },
  emptyStacked: { flexDirection: 'column', alignItems: 'flex-start' },
  emptyIcon: {
    width: 52,
    height: 52,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.accentSoft,
  },
  emptyText: { flexShrink: 1, gap: 4 },
  emptyTitle: {
    fontFamily: fontFamilies.displayRegular,
    fontSize: 22,
    lineHeight: 28,
    color: colors.ink,
  },
  emptyBody: { fontFamily: fontFamilies.body, fontSize: 14.5, lineHeight: 21, color: colors.ink2 },
});
