import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { components } from '@/api-client/schema';
import { GarmentImage } from '@/components/GarmentImage';
import { ColorDots, Pill } from '@/components/ui';
import { pressFeedback } from '@/components/ui/feedback';
import { garmentName } from '@/lib/garment-name';
import { imageUrl } from '@/lib/image-url';
import { colors, fontFamilies, radii, tint } from '@/theme';

type GarmentListItem = Pick<
  components['schemas']['GarmentListItem'],
  | 'id'
  | 'category'
  | 'subcategory'
  | 'status'
  | 'needs_review'
  | 'wear_count'
  | 'created_at'
  | 'img_thumb'
  | 'job'
> & { colors: { name: string; hex: string }[] | null };

const STEP_LABELS: Record<string, string> = {
  preprocess: 'Preparando',
  cutout: 'Recortando',
  color: 'Analizando colores',
  ai_attributes: 'Analizando prenda',
  embedding: 'Calculando similitud',
  consolidate: 'Terminando',
};

/** A garment counts as new while it is unworn and younger than this. */
export const NEW_WINDOW_MS = 7 * 24 * 60 * 60 * 1000;

/** "Nueva": never worn and added within the last week (derived, the API has no such flag). */
export function isNewGarment(
  item: Pick<GarmentListItem, 'wear_count' | 'created_at'>,
  now = Date.now(),
) {
  const created = new Date(item.created_at).getTime();
  return item.wear_count === 0 && !Number.isNaN(created) && now - created <= NEW_WINDOW_MS;
}

type GarmentCardProps = {
  item: GarmentListItem;
  onPress: (id: string) => void;
};

/**
 * One Armario grid cell: the cutout on a tint of its own colour (4:5), state pills, composed
 * name, wear count and colour dots. Without a thumbnail it shows the processing placeholder.
 */
export function GarmentCard({ item, onPress }: GarmentCardProps) {
  const uri = imageUrl(item.img_thumb);
  const name = garmentName(item);
  const dominant = item.colors?.[0]?.hex ?? colors.ink3;
  const dots = (item.colors ?? []).map((entry) => entry.hex);

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Abrir prenda ${name}`}
      onPress={() => onPress(item.id)}
      style={(state) => [styles.card, pressFeedback(state)]}
      testID={`garment-card-${item.id}`}
    >
      <View style={[styles.imageBox, { backgroundColor: tint(dominant) }]}>
        {uri ? (
          <GarmentImage uri={uri} tintColor={dominant} testID="garment-thumb" />
        ) : (
          <Placeholder job={item.job} />
        )}
        <View style={styles.pills}>
          {item.status === 'laundry' ? <Pill label="Lavando" tone="info" dot /> : null}
          {item.status === 'archived' ? <Pill label="Archivada" tone="ghost" /> : null}
          {item.needs_review ? <Pill label="Revisar" tone="warn" testID="review-badge" /> : null}
          {item.status === 'active' && !item.needs_review && isNewGarment(item) ? (
            <Pill label="Nueva" tone="ok" testID="new-badge" />
          ) : null}
        </View>
      </View>
      <View style={styles.meta}>
        <View style={styles.metaText}>
          <Text style={styles.name} numberOfLines={2}>
            {name}
          </Text>
          <Text style={styles.worn}>
            {item.wear_count > 0
              ? `Puesta ${item.wear_count} ${item.wear_count === 1 ? 'vez' : 'veces'}`
              : 'Sin estrenar'}
          </Text>
        </View>
        {dots.length ? <ColorDots colors={dots} ringColor={colors.bg} /> : null}
      </View>
    </Pressable>
  );
}

/** Dashed "+ Añadir prenda" tile that closes the grid. */
export function AddGarmentTile({ onPress }: { onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Añadir prenda"
      onPress={onPress}
      style={(state) => [styles.card, pressFeedback(state)]}
      testID="add-garment-tile"
    >
      <View style={[styles.imageBox, styles.addBox]}>
        <Text style={styles.addPlus}>+</Text>
        <Text style={styles.addLabel}>Añadir prenda</Text>
      </View>
    </Pressable>
  );
}

function Placeholder({ job }: { job: GarmentListItem['job'] }) {
  const failed = job?.status === 'failed';
  const step = job?.step ? STEP_LABELS[job.step] : null;
  const progress = Math.max(0, Math.min(100, job?.progress ?? 0));
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
          accessibilityValue={{ min: 0, max: 100, now: progress }}
        >
          <View style={[styles.fill, { width: `${progress}%` }]} />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { flex: 1, gap: 10 },
  imageBox: { aspectRatio: 4 / 5, borderRadius: radii.md, overflow: 'hidden' },
  pills: { position: 'absolute', top: 10, left: 10, gap: 4, alignItems: 'flex-start' },
  placeholder: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 8, padding: 16 },
  placeholderText: {
    fontFamily: fontFamilies.bodySemiBold,
    fontSize: 14,
    color: colors.ink,
    textAlign: 'center',
  },
  placeholderStep: {
    fontFamily: fontFamilies.body,
    fontSize: 12.5,
    color: colors.ink2,
    textAlign: 'center',
  },
  track: {
    alignSelf: 'stretch',
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.surface3,
    overflow: 'hidden',
  },
  fill: { height: 4, backgroundColor: colors.accent },
  meta: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 8,
    paddingHorizontal: 4,
  },
  metaText: { flex: 1, gap: 2 },
  name: { fontFamily: fontFamilies.bodySemiBold, fontSize: 14, lineHeight: 18, color: colors.ink },
  worn: { fontFamily: fontFamilies.body, fontSize: 12.5, color: colors.ink2 },
  addBox: {
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    borderWidth: 1.5,
    borderStyle: 'dashed',
    borderColor: colors.lineStrong,
  },
  addPlus: {
    fontFamily: fontFamilies.displayRegular,
    fontSize: 32,
    lineHeight: 34,
    color: colors.ink3Text,
  },
  addLabel: { fontFamily: fontFamilies.bodyMedium, fontSize: 13.5, color: colors.ink3Text },
});
