import { useEffect, useRef, useState } from 'react';
import { ScrollView, StyleSheet, Text, useWindowDimensions, View } from 'react-native';

import { IconSymbol } from '@/components/IconSymbol';
import { useReducedMotion } from '@/hooks/useReducedMotion';
import { Button, Eyebrow, Screen, Segmented, Title, type SegmentedOption } from '@/components/ui';
import { colors, fontFamilies, radii, shadows, spacing, TWO_COLUMNS } from '@/theme';

import { AltLooksList, type AltLook } from './AltLookCard';
import { LookCanvas } from './LookCanvas';
import { LookWhyCard, type ReplaceQuestion } from './LookWhyCard';
import { TipCard } from './TipCard';
import { NotIncludedRow, type TodayTryOn } from './TryOnLayer';
import type { LookProposal } from './types';
import { WeatherPill, type Weather } from './WeatherPill';

const HANGER_ICON = { ios: 'tshirt', android: 'checkroom', web: 'checkroom' } as const;
const DROP_ICON = { ios: 'drop', android: 'water_drop', web: 'water_drop' } as const;
const CHART_ICON = {
  ios: 'chart.line.uptrend.xyaxis',
  android: 'trending_up',
  web: 'trending_up',
} as const;

const VIEW_OPTIONS: SegmentedOption<'collage' | 'tryon'>[] = [
  { value: 'collage', label: 'Collage' },
  { value: 'tryon', label: 'Puesto' },
];

/** Why there is no look to show although the wardrobe has garments (offline, a failed request). */
export type TodayProblem = { title: string; text: string; onRetry?: () => void };

export type { ReplaceQuestion };

export type TodayTip = { title: string; text?: string; onPress?: () => void };

type TodayViewProps = {
  /** "Jueves, 1 de octubre". */
  dateLabel: string;
  /** "Buenos días". */
  greeting: string;
  /** Today's look. Undefined while it loads or when nothing can be proposed. */
  proposal?: LookProposal;
  /** The look is being prepared: a neutral placeholder shows instead of the empty copy. */
  generating?: boolean;
  /** No look could be produced for another reason than the wardrobe (shown instead of the copy). */
  problem?: TodayProblem;
  /** The look on screen was saved on an earlier visit (today's could not be generated). */
  savedNote?: string;
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
  /** Try-on of the look on screen; the button, the Collage | Puesto control and the result need it. */
  tryOn?: TodayTryOn;
  wearDisabled?: boolean;
  shuffleDisabled?: boolean;
  /** Why an action is off. */
  actionNote?: string;
  replaceQuestion?: ReplaceQuestion;
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
  generating,
  problem,
  savedNote,
  alternatives = [],
  weather,
  laundryTip,
  usageTip,
  onOpenPiece,
  onOpenAlternative,
  onWear,
  onShuffle,
  tryOn,
  wearDisabled,
  shuffleDisabled,
  actionNote,
  replaceQuestion,
  wardrobeSize = 0,
  onAddGarment,
  onOpenWardrobe,
}: TodayViewProps) {
  const { width } = useWindowDimensions();
  const wide = width >= TWO_COLUMNS;
  const reduced = useReducedMotion();
  const scrollRef = useRef<ScrollView>(null);
  // Offsets from onLayout are relative to the parent: page inside the scroll content, look inside the page.
  const pageTop = useRef(0);
  const lookTop = useRef(0);
  // On one column the canvas is above the card that holds the button: bring it into view so the
  // progress is seen starting. Side by side (wide) both are already on screen.
  const lookId = proposal?.pieces.map((piece) => piece.garmentId).join(',') ?? '';
  const [pendingFor, setPendingFor] = useState<string | null>(null);
  const showTryOn = () => {
    tryOn?.onTryOn();
    if (!wide) setPendingFor(lookId);
  };
  const toggleShown = !!tryOn?.showToggle;
  // The pending scroll belongs to the look it was asked on: shuffling must not fire it on another one.
  if (pendingFor !== null && pendingFor !== lookId) setPendingFor(null);
  const pendingScroll = pendingFor === lookId;
  // Scroll once the control is inserted above the canvas: the layout shift would cancel an earlier scroll.
  useEffect(() => {
    if (!pendingScroll || !toggleShown) return undefined;
    const frame = requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({
        y: Math.max(0, pageTop.current + lookTop.current - spacing.md),
        animated: !reduced,
      });
      setPendingFor(null);
    });
    return () => cancelAnimationFrame(frame);
  }, [pendingScroll, toggleShown, reduced]);
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
    <Screen testID="today-screen" scrollRef={scrollRef}>
      <View
        style={styles.page}
        onLayout={(event) => {
          pageTop.current = event.nativeEvent.layout.y;
        }}
      >
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
        {savedNote && proposal ? (
          <Text style={styles.savedNote} testID="saved-note">
            {savedNote}
          </Text>
        ) : null}

        {proposal ? (
          <View
            style={[styles.look, wide && styles.lookWide]}
            onLayout={(event) => {
              lookTop.current = event.nativeEvent.layout.y;
            }}
          >
            <View style={[styles.canvasStack, wide && styles.canvasCol]}>
              {tryOn?.showToggle ? (
                <Segmented
                  accessibilityLabel="Vista del look"
                  options={VIEW_OPTIONS}
                  value={tryOn.mode}
                  onChange={tryOn.onModeChange}
                />
              ) : null}
              <LookCanvas
                pieces={proposal.pieces}
                formalityLabel={proposal.formalityLabel}
                matchPercent={proposal.matchPercent}
                aspectRatio={wide ? 1.28 : 0.8}
                tryOn={tryOn?.canvas}
              />
              {tryOn?.mode === 'tryon' && tryOn.canvas.status.phase === 'done' ? (
                <NotIncludedRow pieces={tryOn.notIncluded} />
              ) : null}
            </View>
            <View style={wide ? [styles.cardCol, styles.cardColCentered] : undefined}>
              <LookWhyCard
                name={proposal.name}
                reasons={proposal.reasons}
                pieces={proposal.pieces}
                onOpenPiece={onOpenPiece}
                onWear={onWear}
                onShuffle={onShuffle}
                onTryOn={tryOn?.canTry ? showTryOn : undefined}
                tryOnDisabled={tryOn?.tryOnDisabled}
                wearDisabled={wearDisabled}
                shuffleDisabled={shuffleDisabled}
                note={actionNote}
                replaceQuestion={replaceQuestion}
              />
            </View>
          </View>
        ) : (
          <View style={[styles.look, wide && styles.lookWide]}>
            {wardrobeSize === 'loading' || (generating && soon) ? (
              <View
                style={[styles.empty, styles.emptyLoading, wide && styles.canvasCol]}
                testID="empty-state-loading"
              />
            ) : problem ? (
              <View style={[styles.empty, wide && styles.canvasCol]} testID="problem-state">
                <View style={styles.emptyIcon}>
                  <IconSymbol name={HANGER_ICON} size={28} color={colors.accentText} />
                </View>
                <Text accessibilityRole="header" style={styles.emptyTitle}>
                  {problem.title}
                </Text>
                <Text style={styles.emptyText}>{problem.text}</Text>
                {problem.onRetry ? (
                  <Button variant="secondary" label="Reintentar" onPress={problem.onRetry} />
                ) : null}
              </View>
            ) : soon ? (
              <View style={[styles.empty, wide && styles.canvasCol]} testID="no-looks-state">
                <View style={styles.emptyIcon}>
                  <IconSymbol name={HANGER_ICON} size={28} color={colors.accentText} />
                </View>
                <Text accessibilityRole="header" style={styles.emptyTitle}>
                  Todavía no podemos armar un look
                </Text>
                <Text style={styles.emptyText}>
                  {`${hasGarments ? `Tienes ${wardrobeSize} ${wardrobeSize === 1 ? 'prenda' : 'prendas'} en tu armario, pero faltan ` : 'Faltan '}prendas activas para un look completo: una parte de arriba, un pantalón y calzado, o un vestido y calzado.`}
                </Text>
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
  canvasStack: { gap: spacing.md },
  canvasCol: { flex: 1.25 },
  tipColumn: { gap: spacing.md, justifyContent: 'flex-start' },
  cardCol: { flex: 1 },
  // The card keeps its own height, centred beside the canvas, instead of stretching over empty space.
  cardColCentered: { alignSelf: 'center' },
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
  savedNote: { fontFamily: fontFamilies.body, fontSize: 14, lineHeight: 20, color: colors.ink2 },
  tips: { gap: spacing.md },
  tipsWide: { flexDirection: 'row' },
  tip: { flexGrow: 1, flexShrink: 1 },
});
