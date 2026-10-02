import { Pressable, StyleSheet, Text, View } from 'react-native';

import { GarmentImage } from '@/components/GarmentImage';
import type { components } from '@/api-client/schema';
import { imageUrl } from '@/lib/image-url';
import { categoryLabel } from '@/lib/labels';
import { colors, fontFamilies, fontSizes, radii, spacing } from '@/theme';

type GarmentListItem = Pick<
  components['schemas']['GarmentListItem'],
  'id' | 'category' | 'needs_review' | 'img_thumb' | 'job'
>;

const STEP_LABELS: Record<string, string> = {
  preprocess: 'Preparando',
  cutout: 'Recortando',
  color: 'Analizando colores',
  ai_attributes: 'Analizando prenda',
  embedding: 'Calculando similitud',
  consolidate: 'Terminando',
};

type GarmentCardProps = {
  item: GarmentListItem;
  onPress: (id: string) => void;
};

/** One Armario grid cell: thumbnail or processing placeholder, category, review badge. */
export function GarmentCard({ item, onPress }: GarmentCardProps) {
  const uri = imageUrl(item.img_thumb);
  const label = categoryLabel(item.category);

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Abrir prenda ${label}`}
      onPress={() => onPress(item.id)}
      style={styles.card}
      testID={`garment-card-${item.id}`}
    >
      <View style={styles.imageBox}>
        {uri ? <GarmentImage uri={uri} testID="garment-thumb" /> : <Placeholder job={item.job} />}
        {item.needs_review ? (
          <View style={styles.badge} testID="review-badge">
            <Text style={styles.badgeText}>Revisar</Text>
          </View>
        ) : null}
      </View>
      <Text style={styles.category} numberOfLines={1}>
        {label}
      </Text>
    </Pressable>
  );
}

function Placeholder({ job }: { job: GarmentListItem['job'] }) {
  const failed = job?.status === 'failed';
  const step = job?.step ? STEP_LABELS[job.step] : null;
  return (
    <View style={styles.placeholder} testID="garment-processing">
      <Text style={styles.placeholderText}>
        {failed ? 'Falló el procesamiento' : 'Procesando…'}
      </Text>
      {!failed && step ? <Text style={styles.placeholderStep}>{step}</Text> : null}
      {!failed && job ? (
        <View
          accessible
          style={styles.track}
          accessibilityRole="progressbar"
          accessibilityValue={{ min: 0, max: 100, now: Math.max(0, Math.min(100, job.progress)) }}
        >
          <View style={[styles.fill, { width: `${Math.max(0, Math.min(100, job.progress))}%` }]} />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  // The garment stands on a plinth: a light tile with generous inner padding and only a hairline edge.
  card: {
    flex: 1,
    backgroundColor: colors.plinth,
    borderRadius: radii.tile,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.hairline,
    padding: spacing.md,
    gap: spacing.sm,
  },
  imageBox: { aspectRatio: 1, borderRadius: radii.sm, overflow: 'hidden' },
  placeholder: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    padding: spacing.sm,
    backgroundColor: colors.stone,
    borderRadius: radii.sm,
  },
  placeholderText: {
    fontFamily: fontFamilies.bodySemiBold,
    fontSize: fontSizes.small,
    color: colors.charcoal,
    textAlign: 'center',
  },
  placeholderStep: {
    fontFamily: fontFamilies.body,
    fontSize: fontSizes.caption,
    color: colors.muted,
    textAlign: 'center',
  },
  track: {
    alignSelf: 'stretch',
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.hairline,
    overflow: 'hidden',
  },
  fill: { height: 4, backgroundColor: colors.olive },
  badge: {
    position: 'absolute',
    top: 0,
    left: 0,
    paddingVertical: 2,
    paddingHorizontal: spacing.sm,
    borderRadius: radii.xs,
    backgroundColor: colors.brass,
  },
  badgeText: {
    fontFamily: fontFamilies.bodySemiBold,
    fontSize: fontSizes.caption,
    color: colors.onBrass,
  },
  category: {
    fontFamily: fontFamilies.bodyMedium,
    fontSize: fontSizes.small,
    color: colors.charcoal,
  },
});
