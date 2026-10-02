import { StyleSheet, Text, useWindowDimensions, View } from 'react-native';

import { IconSymbol } from '@/components/IconSymbol';
import { Button, Eyebrow, Screen, Title } from '@/components/ui';
import { colors, fontFamilies, radii, shadows, spacing, TWO_COLUMNS } from '@/theme';

import { AltLooksList, type AltLook } from './AltLookCard';
import { LookCanvas } from './LookCanvas';
import { LookWhyCard } from './LookWhyCard';
import { TipCard } from './TipCard';
import type { LookProposal } from './types';
import { WeatherPill, type Weather } from './WeatherPill';

const HANGER_ICON = { ios: 'tshirt', android: 'checkroom', web: 'checkroom' } as const;
const DROP_ICON = { ios: 'drop', android: 'water_drop', web: 'water_drop' } as const;
const CHART_ICON = {
  ios: 'chart.line.uptrend.xyaxis',
  android: 'trending_up',
  web: 'trending_up',
} as const;

export type TodayTip = { title: string; text?: string; onPress?: () => void };

type TodayViewProps = {
  /** "Jueves, 1 de octubre". */
  dateLabel: string;
  /** "Buenos días". */
  greeting: string;
  /** Today's look. Undefined until the outfit engine exists: the empty state shows instead. */
  proposal?: LookProposal;
  alternatives?: AltLook[];
  weather?: Weather;
  /** Laundry notice; omitted when there is nothing in the basket. */
  laundryTip?: TodayTip;
  /** Wardrobe-usage notice; omitted when it cannot be computed. */
  usageTip?: TodayTip;
  onOpenPiece?: (garmentId: string) => void;
  onOpenAlternative?: (id: string) => void;
  onWear?: () => void;
  onShuffle?: () => void;
  /**
   * Garments in the wardrobe (active + laundry). Decides what the no-proposal state says:
   * `loading` shows a neutral placeholder, `unknown` (the count failed) avoids claiming a number.
   */
  wardrobeSize?: number | 'loading' | 'unknown';
  onAddGarment: () => void;
  onOpenWardrobe: () => void;
};

/**
 * Hoy: date and greeting, the look of the day (canvas + "why" card) with its alternatives, and
 * two notices. Everything coming from the engine or the weather arrives through optional props
 * and is simply absent without data.
 */
export function TodayView({
  dateLabel,
  greeting,
  proposal,
  alternatives = [],
  weather,
  laundryTip,
  usageTip,
  onOpenPiece,
  onOpenAlternative,
  onWear,
  onShuffle,
  wardrobeSize = 0,
  onAddGarment,
  onOpenWardrobe,
}: TodayViewProps) {
  const { width } = useWindowDimensions();
  const wide = width >= TWO_COLUMNS;
  const hasGarments = typeof wardrobeSize === 'number' && wardrobeSize > 0;
  const soon = hasGarments || wardrobeSize === 'unknown';
  const tips =
    laundryTip || usageTip ? (
      <>
        {laundryTip ? (
          <View style={styles.tip}>
            <TipCard icon={DROP_ICON} tone="info" {...laundryTip} testID="tip-laundry" />
          </View>
        ) : null}
        {usageTip ? (
          <View style={styles.tip}>
            <TipCard icon={CHART_ICON} tone="accent" {...usageTip} testID="tip-usage" />
          </View>
        ) : null}
      </>
    ) : null;

  return (
    <Screen testID="today-screen">
      <View style={styles.page}>
        <View style={[styles.header, wide && styles.headerWide]}>
          <View style={styles.titleBlock}>
            <Eyebrow>{dateLabel}</Eyebrow>
            {proposal ? (
              <Title size={wide ? 'hero' : 'page'} accent="proponemos">
                {`${greeting}.\nHoy te proponemos…`}
              </Title>
            ) : hasGarments ? (
              <Title size={wide ? 'hero' : 'page'} accent="armario">
                {`${greeting}.\nTu armario está listo.`}
              </Title>
            ) : wardrobeSize === 0 ? (
              <Title size={wide ? 'hero' : 'page'} accent="armario">
                {`${greeting}.\nEmpecemos por tu armario.`}
              </Title>
            ) : (
              <Title size={wide ? 'hero' : 'page'}>{`${greeting}.`}</Title>
            )}
          </View>
          <WeatherPill weather={weather} />
        </View>

        {proposal ? (
          <View style={[styles.look, wide && styles.lookWide]}>
            <View style={wide ? styles.canvasCol : undefined}>
              <LookCanvas
                pieces={proposal.pieces}
                formalityLabel={proposal.formalityLabel}
                matchPercent={proposal.matchPercent}
                aspectRatio={wide ? 1.28 : 0.8}
              />
            </View>
            <View style={wide ? styles.cardCol : undefined}>
              <LookWhyCard
                name={proposal.name}
                reasons={proposal.reasons}
                pieces={proposal.pieces}
                onOpenPiece={onOpenPiece}
                onWear={onWear}
                onShuffle={onShuffle}
                style={wide ? styles.fill : undefined}
              />
            </View>
          </View>
        ) : (
          <View style={[styles.look, wide && styles.lookWide]}>
            {wardrobeSize === 'loading' ? (
              <View
                style={[styles.empty, styles.emptyLoading, wide && styles.canvasCol]}
                testID="empty-state-loading"
              />
            ) : soon ? (
              <View style={[styles.empty, wide && styles.canvasCol]} testID="soon-state">
                <View style={styles.emptyIcon}>
                  <IconSymbol name={HANGER_ICON} size={28} color={colors.accentText} />
                </View>
                <Text accessibilityRole="header" style={styles.emptyTitle}>
                  Tus propuestas diarias llegan pronto
                </Text>
                {hasGarments ? (
                  <Text style={styles.emptyText}>
                    {`Ya tienes ${wardrobeSize} ${wardrobeSize === 1 ? 'prenda' : 'prendas'} en tu armario. Cuando activemos las sugerencias, aquí verás tu look de cada día.`}
                  </Text>
                ) : null}
                <Button variant="secondary" label="Ver tu armario" onPress={onOpenWardrobe} />
              </View>
            ) : (
              <View style={[styles.empty, wide && styles.canvasCol]} testID="empty-state">
                <View style={styles.emptyIcon}>
                  <IconSymbol name={HANGER_ICON} size={28} color={colors.accentText} />
                </View>
                <Text accessibilityRole="header" style={styles.emptyTitle}>
                  Aún no tienes suficientes prendas para generar un outfit
                </Text>
                <Text style={styles.emptyText}>
                  Añade algunas prendas a tu armario y aquí verás tu primera propuesta del día.
                </Text>
                <Button label="Añadir prendas" onPress={onAddGarment} />
              </View>
            )}
            {wide && tips ? <View style={[styles.cardCol, styles.tipColumn]}>{tips}</View> : null}
          </View>
        )}

        {proposal ? <AltLooksList looks={alternatives} onSelect={onOpenAlternative} /> : null}

        {tips && (proposal || !wide) ? (
          <View style={[styles.tips, wide && styles.tipsWide]}>{tips}</View>
        ) : null}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  page: { gap: spacing.xxl, paddingTop: spacing.md },
  header: { gap: 10, alignItems: 'flex-start' },
  headerWide: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end' },
  titleBlock: { gap: 10 },
  look: { gap: spacing.xl },
  lookWide: { flexDirection: 'row', alignItems: 'stretch' },
  canvasCol: { flex: 1.25 },
  fill: { flexGrow: 1 },
  tipColumn: { gap: spacing.md, justifyContent: 'flex-start' },
  cardCol: { flex: 1 },
  empty: {
    alignItems: 'flex-start',
    gap: 14,
    padding: 28,
    borderRadius: radii.lg,
    backgroundColor: colors.surface,
    boxShadow: shadows.card,
  },
  emptyLoading: { minHeight: 220 },
  emptyIcon: {
    width: 56,
    height: 56,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.accentSoft,
  },
  emptyTitle: {
    maxWidth: 560,
    fontFamily: fontFamilies.displayRegular,
    fontSize: 28,
    lineHeight: 33,
    color: colors.ink,
  },
  emptyText: {
    maxWidth: 520,
    fontFamily: fontFamilies.body,
    fontSize: 15,
    lineHeight: 22,
    color: colors.ink2,
  },
  tips: { gap: spacing.md },
  tipsWide: { flexDirection: 'row' },
  tip: { flexGrow: 1, flexShrink: 1 },
});
