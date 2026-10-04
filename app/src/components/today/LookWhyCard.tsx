import { useEffect, useRef } from 'react';
import { Pressable, StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';

import { GarmentImage } from '@/components/GarmentImage';
import { IconSymbol } from '@/components/IconSymbol';
import { Button, Card, Eyebrow } from '@/components/ui';
import { pressFeedback } from '@/components/ui/feedback';
import { colors, fontFamilies, radii } from '@/theme';

import type { LookPiece, LookReason } from './types';

const CHECK_ICON = { ios: 'checkmark', android: 'check', web: 'check' } as const;
const SHUFFLE_ICON = {
  ios: 'arrow.triangle.2.circlepath',
  android: 'refresh',
  web: 'refresh',
} as const;

/** The "¿Cambiarlo por este?" question shown when today already has a logged outfit. */
export type ReplaceQuestion = { busy: boolean; onConfirm: () => void; onCancel: () => void };

type LookWhyCardProps = {
  /** Look name; hidden when absent. */
  name?: string;
  reasons?: LookReason[];
  pieces: LookPiece[];
  /** Opens a piece's Detalle. Without it the thumbnails are not pressable. */
  onOpenPiece?: (garmentId: string) => void;
  /** "Me lo pongo". The button is hidden when absent. */
  onWear?: () => void;
  /** "Otra sugerencia". The button is hidden when absent. */
  onShuffle?: () => void;
  /** "Me lo pongo" is shown but off (offline, or a request is running). */
  wearDisabled?: boolean;
  /** "Otra sugerencia" is shown but off. */
  shuffleDisabled?: boolean;
  /** Replaces the actions with the replace question while it is pending. */
  replaceQuestion?: ReplaceQuestion;
  /** Why an action is off (calm, under the buttons). */
  note?: string;
  /** Layout overrides (Hoy stretches the card to the canvas height). */
  style?: StyleProp<ViewStyle>;
  testID?: string;
};

/** Right-hand card of Hoy: why this look, its pieces, and the two actions. */
export function LookWhyCard({
  name,
  reasons = [],
  pieces,
  onOpenPiece,
  onWear,
  onShuffle,
  wearDisabled,
  shuffleDisabled,
  note,
  replaceQuestion,
  style,
  testID,
}: LookWhyCardProps) {
  // The pressed button is replaced by the question: move focus to it (web; native announces it).
  const questionRef = useRef<View>(null);
  const asking = !!replaceQuestion;
  useEffect(() => {
    if (asking) (questionRef.current as unknown as HTMLElement | null)?.focus?.();
  }, [asking]);
  const thumbs = pieces.filter((piece) => piece.imageUri);
  return (
    <Card style={[styles.card, style]} testID={testID}>
      <Eyebrow>Look del día</Eyebrow>
      {name ? (
        <Text accessibilityRole="header" style={styles.name}>
          {name}
        </Text>
      ) : null}
      {reasons.length ? (
        <View style={styles.reasons}>
          {reasons.map((reason) => (
            <View key={reason.title} style={styles.reason}>
              <View style={styles.reasonIcon}>
                <IconSymbol name={reason.icon} size={16} color={colors.ink} />
              </View>
              <Text style={styles.reasonText}>
                <Text style={styles.reasonTitle}>{reason.title}</Text> {reason.text}
              </Text>
            </View>
          ))}
        </View>
      ) : null}
      {thumbs.length ? (
        <View style={styles.pieces}>
          {thumbs.map((piece) => {
            const content = (
              <GarmentImage
                uri={piece.imageUri as string}
                tintColor={piece.color ?? colors.ink3}
                accessibilityLabel={piece.name}
              />
            );
            return onOpenPiece ? (
              <Pressable
                key={piece.garmentId}
                accessibilityRole="button"
                accessibilityLabel={`Abrir prenda ${piece.name}`}
                onPress={() => onOpenPiece(piece.garmentId)}
                style={(state) => [styles.piece, pressFeedback(state)]}
              >
                {content}
              </Pressable>
            ) : (
              <View key={piece.garmentId} style={styles.piece}>
                {content}
              </View>
            );
          })}
        </View>
      ) : null}
      {replaceQuestion ? (
        <View
          ref={questionRef}
          tabIndex={-1}
          accessibilityLiveRegion="polite"
          style={styles.question}
          testID="replace-question"
        >
          <Text accessibilityRole="header" style={styles.questionTitle}>
            Hoy ya registraste otro outfit
          </Text>
          <Text style={styles.questionText}>¿Cambiarlo por este?</Text>
          <View style={styles.questionActions}>
            <Button
              label="Cambiar por este"
              onPress={replaceQuestion.onConfirm}
              disabled={replaceQuestion.busy}
            />
            <Button
              variant="secondary"
              label="Mantener el anterior"
              onPress={replaceQuestion.onCancel}
              disabled={replaceQuestion.busy}
            />
          </View>
        </View>
      ) : onWear || onShuffle ? (
        <View style={styles.actions}>
          {onWear ? (
            <View style={styles.wear}>
              <Button
                label="Me lo pongo"
                icon={CHECK_ICON}
                onPress={onWear}
                disabled={wearDisabled}
              />
            </View>
          ) : null}
          {onShuffle ? (
            <Button
              icon={SHUFFLE_ICON}
              accessibilityLabel="Otra sugerencia"
              variant="secondary"
              onPress={onShuffle}
              disabled={shuffleDisabled}
            />
          ) : null}
        </View>
      ) : null}
      {note ? (
        <Text style={styles.note} testID="look-note">
          {note}
        </Text>
      ) : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  card: { padding: 24, gap: 6 },
  name: {
    fontFamily: fontFamilies.displayRegular,
    fontSize: 28,
    lineHeight: 32,
    color: colors.ink,
  },
  reasons: { gap: 12, marginTop: 12, marginBottom: 10 },
  reason: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  reasonIcon: {
    width: 32,
    height: 32,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface2,
  },
  reasonText: {
    flex: 1,
    fontFamily: fontFamilies.body,
    fontSize: 14,
    lineHeight: 20,
    color: colors.ink2,
  },
  reasonTitle: { fontFamily: fontFamilies.bodySemiBold, color: colors.ink },
  pieces: { flexDirection: 'row', gap: 8, marginTop: 8, marginBottom: 14 },
  piece: { flex: 1, maxWidth: 120, aspectRatio: 1, borderRadius: radii.tile, overflow: 'hidden' },
  actions: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 'auto', paddingTop: 6 },
  wear: { flex: 1 },
  question: { gap: 6, marginTop: 'auto', paddingTop: 6 },
  questionTitle: {
    fontFamily: fontFamilies.display,
    fontSize: 18,
    lineHeight: 24,
    color: colors.ink,
  },
  questionText: { fontFamily: fontFamilies.body, fontSize: 14, lineHeight: 20, color: colors.ink2 },
  questionActions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, paddingTop: 4 },
  note: {
    marginTop: 10,
    fontFamily: fontFamilies.body,
    fontSize: 13,
    lineHeight: 18,
    color: colors.ink2,
  },
});
