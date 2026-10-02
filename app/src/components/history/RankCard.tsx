import { Image } from 'expo-image';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Pill } from '@/components/ui';
import { pressFeedback } from '@/components/ui/feedback';
import { colors, fontFamilies, radii, shadows, tint } from '@/theme';

export type RankItem = {
  id: string;
  name: string;
  /** "12 usos", "Sin estrenar", "Hace 80 días". */
  detail: string;
  /** Dominant colour (hex) for the tile behind the thumbnail. */
  color: string;
  thumbUri: string | null;
  /** 0..1 bar next to the row (usage relative to the list's maximum); omitted = no bar. */
  usage?: number;
};

type RankCardProps = {
  title: string;
  items: RankItem[];
  onOpen: (id: string) => void;
  /**
   * "Sugerir" button per row. There is no endpoint that puts a garment into the suggestions yet,
   * so screens do not pass it and the button is not drawn.
   */
  onSuggest?: (id: string) => void;
  testID?: string;
};

/** Card with a title and rows: tinted thumbnail, name, detail, then a usage bar or an action. */
export function RankCard({ title, items, onOpen, onSuggest, testID }: RankCardProps) {
  return (
    <View style={styles.card} testID={testID}>
      <Text accessibilityRole="header" style={styles.title}>
        {title}
      </Text>
      {items.map((item, index) => (
        <View key={item.id} style={[styles.row, index > 0 && styles.separator]}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Abrir prenda ${item.name}`}
            onPress={() => onOpen(item.id)}
            style={(state) => [styles.open, pressFeedback(state)]}
          >
            <View style={[styles.thumb, { backgroundColor: tint(item.color) }]}>
              {item.thumbUri ? (
                <Image source={{ uri: item.thumbUri }} style={styles.image} contentFit="contain" />
              ) : null}
            </View>
            <View style={styles.text}>
              <Text style={styles.name} numberOfLines={1}>
                {item.name}
              </Text>
              <Text style={styles.detail}>{item.detail}</Text>
            </View>
            {item.usage !== undefined ? (
              <View
                accessible
                accessibilityRole="progressbar"
                accessibilityLabel={`Uso de ${item.name}`}
                accessibilityValue={{ min: 0, max: 100, now: Math.round(item.usage * 100) }}
                style={styles.track}
              >
                <View style={[styles.fill, { width: `${Math.round(item.usage * 100)}%` }]} />
              </View>
            ) : null}
          </Pressable>
          {onSuggest ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`Sugerir ${item.name}`}
              onPress={() => onSuggest(item.id)}
              style={(state) => [styles.suggest, pressFeedback(state)]}
            >
              <Pill label="Sugerir" />
            </Pressable>
          ) : null}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flex: 1,
    padding: 20,
    borderRadius: radii.md,
    backgroundColor: colors.surface,
    boxShadow: shadows.card,
  },
  title: { fontFamily: fontFamilies.display, fontSize: 17, lineHeight: 24, color: colors.ink },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  separator: { borderTopWidth: 1, borderTopColor: colors.line },
  open: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 60 },
  thumb: {
    width: 44,
    height: 44,
    borderRadius: 12,
    overflow: 'hidden',
    padding: 3,
  },
  image: { width: '100%', height: '100%' },
  text: { flex: 1, minWidth: 90, gap: 1 },
  name: { fontFamily: fontFamilies.bodySemiBold, fontSize: 14, lineHeight: 19, color: colors.ink },
  detail: { fontFamily: fontFamilies.body, fontSize: 12.5, lineHeight: 17, color: colors.ink2 },
  track: {
    flexGrow: 1,
    flexBasis: 64,
    maxWidth: 200,
    height: 6,
    borderRadius: 3,
    overflow: 'hidden',
    backgroundColor: colors.surface2,
  },
  fill: { height: 6, borderRadius: 3, backgroundColor: colors.ink },
  suggest: { minHeight: 44, justifyContent: 'center' },
});
