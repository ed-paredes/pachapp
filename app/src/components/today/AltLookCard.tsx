import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { pressFeedback } from '@/components/ui/feedback';
import { colors, fontFamilies, radii, tint } from '@/theme';

import { LookItems } from './LookCanvas';
import { matchLabel, type LookPiece } from './types';

export type AltLook = {
  id: string;
  name: string;
  pieces: LookPiece[];
  matchPercent?: number;
};

type AltLookCardProps = { look: AltLook; onPress?: (id: string) => void };

/** Alternative look: tinted card with a miniature collage, its name and a one-line summary. */
export function AltLookCard({ look, onPress }: AltLookCardProps) {
  const lead = look.pieces.find((piece) => piece.color)?.color ?? colors.ink3;
  const count = look.pieces.length;
  const summary = [`${count} ${count === 1 ? 'prenda' : 'prendas'}`];
  if (look.matchPercent !== undefined) summary.push(matchLabel(look.matchPercent));

  const body = (
    <>
      <View style={styles.mini}>
        <LookItems pieces={look.pieces} flat />
      </View>
      <Text style={styles.name} numberOfLines={2}>
        {look.name}
      </Text>
      <Text style={styles.summary}>{summary.join(' · ')}</Text>
    </>
  );
  const frame = [styles.card, { backgroundColor: tint(lead) }];
  return onPress ? (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Ver look ${look.name}`}
      onPress={() => onPress(look.id)}
      style={(state) => [frame, pressFeedback(state)]}
    >
      {body}
    </Pressable>
  ) : (
    <View style={frame}>{body}</View>
  );
}

type AltLooksListProps = { looks: AltLook[]; onSelect?: (id: string) => void };

/** "Otras opciones para hoy": horizontal list of alternatives; not rendered when empty. */
export function AltLooksList({ looks, onSelect }: AltLooksListProps) {
  if (!looks.length) return null;
  return (
    <View style={styles.section}>
      <Text accessibilityRole="header" style={styles.heading}>
        Otras opciones para hoy
      </Text>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.row}
        testID="alt-looks"
      >
        {looks.map((look) => (
          <AltLookCard key={look.id} look={look} onPress={onSelect} />
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: 12 },
  heading: { fontFamily: fontFamilies.display, fontSize: 20, lineHeight: 26, color: colors.ink },
  row: { gap: 12, paddingBottom: 6 },
  card: { width: 208, borderRadius: radii.md, padding: 12, gap: 2 },
  mini: {
    height: 150,
    borderRadius: 12,
    marginBottom: 10,
    backgroundColor: 'rgba(255,255,255,0.45)',
    overflow: 'hidden',
  },
  name: {
    fontFamily: fontFamilies.bodySemiBold,
    fontSize: 14,
    lineHeight: 19,
    minHeight: 38, // two lines: cards in a row keep the same height
    color: colors.ink,
  },
  summary: { fontFamily: fontFamilies.body, fontSize: 12.5, color: colors.ink2 },
});
