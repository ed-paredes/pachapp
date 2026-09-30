import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import type { components } from '@/api-client/schema';
import { imageUrl } from '@/lib/image-url';
import { categoryLabel } from '@/lib/labels';

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
        {uri ? (
          <Image
            source={{ uri }}
            style={styles.image}
            resizeMode="contain"
            testID="garment-thumb"
          />
        ) : (
          <Placeholder job={item.job} />
        )}
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
  card: { flex: 1, gap: 6 },
  imageBox: {
    aspectRatio: 1,
    borderRadius: 10,
    backgroundColor: '#F1F5F9',
    overflow: 'hidden',
  },
  image: { width: '100%', height: '100%' },
  placeholder: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 6, padding: 8 },
  placeholderText: { fontSize: 13, fontWeight: '600', textAlign: 'center' },
  placeholderStep: { fontSize: 12, opacity: 0.7, textAlign: 'center' },
  track: {
    alignSelf: 'stretch',
    height: 6,
    borderRadius: 3,
    backgroundColor: '#E4E7EC',
    overflow: 'hidden',
  },
  fill: { height: 6, backgroundColor: '#208AEF' },
  badge: {
    position: 'absolute',
    top: 6,
    right: 6,
    paddingVertical: 2,
    paddingHorizontal: 8,
    borderRadius: 10,
    backgroundColor: '#F79009',
  },
  badgeText: { color: '#fff', fontSize: 12, fontWeight: '700' },
  category: { fontSize: 13, fontWeight: '500' },
});
