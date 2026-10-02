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
  style,
  testID,
}: LookWhyCardProps) {
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
      {onWear || onShuffle ? (
        <View style={styles.actions}>
          {onWear ? (
            <View style={styles.wear}>
              <Button label="Me lo pongo" icon={CHECK_ICON} onPress={onWear} />
            </View>
          ) : null}
          {onShuffle ? (
            <Button
              icon={SHUFFLE_ICON}
              accessibilityLabel="Otra sugerencia"
              variant="secondary"
              onPress={onShuffle}
            />
          ) : null}
        </View>
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
});
