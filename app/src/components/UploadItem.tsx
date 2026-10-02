import { Image } from 'expo-image';
import { useRouter } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import { GarmentImage } from '@/components/GarmentImage';
import { ProgressBar } from '@/components/add/ProgressBar';
import { ScanLine } from '@/components/add/ScanLine';
import { uploadStatus } from '@/components/add/upload-status';
import { Button, Card, ColorDots, Pill } from '@/components/ui';
import { useGarment } from '@/hooks/useGarments';
import { useRetryGarment } from '@/hooks/useGarmentMutations';
import { useJob } from '@/hooks/useJob';
import type { QueueItem } from '@/hooks/useUploadQueue';
import { garmentName } from '@/lib/garment-name';
import { imageUrl } from '@/lib/image-url';
import { categoryLabel } from '@/lib/labels';
import { LOW_RES_NOTE } from '@/lib/photos';
import { colors, fontFamilies, radii, tint } from '@/theme';

type UploadItemProps = {
  item: QueueItem;
  onRetryUpload: (key: string) => void;
  onDismiss: (key: string) => void;
};

/** One photo on Añadir with its own state, progress and actions (UI-REQ-006/018/019). */
export function UploadItem({ item, onRetryUpload, onDismiss }: UploadItemProps) {
  if (item.phase === 'queued' && item.jobId && item.garmentId) {
    return <ProcessingItem item={item} jobId={item.jobId} garmentId={item.garmentId} />;
  }

  const status = uploadStatus(item.phase);
  return (
    <ItemCard
      item={item}
      status={status}
      scanning={false}
      footer={
        status.kind === 'failed' ? (
          <>
            <Text style={styles.error}>{item.error}</Text>
            <View style={styles.actions}>
              {item.photo ? (
                <Button
                  label="Reintentar"
                  accessibilityLabel={`Reintentar subida de ${item.name}`}
                  onPress={() => onRetryUpload(item.key)}
                />
              ) : null}
              <Button
                label="Quitar"
                accessibilityLabel={`Quitar ${item.name}`}
                variant="secondary"
                onPress={() => onDismiss(item.key)}
              />
            </View>
          </>
        ) : null
      }
    />
  );
}

function ProcessingItem({
  item,
  jobId,
  garmentId,
}: {
  item: QueueItem;
  jobId: string;
  garmentId: string;
}) {
  const router = useRouter();
  const job = useJob(jobId);
  const retry = useRetryGarment(garmentId);
  const data = job.data;
  const status = uploadStatus(item.phase, data);
  // Name, colours and confidence only exist once the garment has been analysed.
  const garment = useGarment(status.kind === 'done' ? garmentId : undefined).data;

  return (
    <ItemCard
      item={item}
      status={status}
      scanning={status.kind === 'analysing'}
      garment={garment}
      footer={
        <>
          {status.kind === 'failed' ? (
            <>
              <Text style={styles.error}>{data?.error ?? 'No se pudo procesar la foto.'}</Text>
              {retry.error ? <Text style={styles.error}>{retry.error.message}</Text> : null}
              <View style={styles.actions}>
                <Button
                  label="Reintentar"
                  accessibilityLabel={`Reintentar ${item.name}`}
                  onPress={() => retry.mutate()}
                  disabled={retry.isPending}
                />
              </View>
            </>
          ) : null}
          {job.isError ? <Text style={styles.error}>{job.error.message}</Text> : null}
          {status.kind === 'done' ? (
            <View style={styles.actions}>
              <Button
                label="Revisar"
                accessibilityLabel={`Revisar ${item.name}`}
                variant="secondary"
                onPress={() => router.push(`/review/${garmentId}`)}
              />
            </View>
          ) : null}
        </>
      }
    />
  );
}

type Garment = ReturnType<typeof useGarment>['data'];

function ItemCard({
  item,
  status,
  scanning,
  garment,
  footer,
}: {
  item: QueueItem;
  status: ReturnType<typeof uploadStatus>;
  scanning: boolean;
  garment?: Garment;
  footer: React.ReactNode;
}) {
  const done = status.kind === 'done';
  const hasBar =
    status.kind === 'uploading' || status.kind === 'queued' || status.kind === 'analysing';
  const dotColors = (garment?.colors ?? []).map((entry) => entry.hex);
  const confidence = garment?.ai_confidence?.category?.confidence;
  const title = done && garment ? garmentName(garment) : item.name;

  return (
    <Card style={styles.card} testID={`upload-item-${item.key}`}>
      <View style={styles.row}>
        <Thumb item={item} garment={done ? garment : undefined} scanning={scanning} />
        <View style={styles.body}>
          <View style={styles.head}>
            <Text style={styles.name} numberOfLines={2}>
              {title}
            </Text>
            <Pill label={status.label} tone={status.tone} dot={status.kind !== 'done'} />
          </View>
          {done && garment ? (
            <View style={styles.details}>
              <Text style={styles.meta}>{categoryLabel(garment.category)}</Text>
              {dotColors.length ? <ColorDots colors={dotColors} /> : null}
              {typeof confidence === 'number' ? (
                <Text style={styles.confidence}>{`${Math.round(confidence * 100)} % seguro`}</Text>
              ) : null}
            </View>
          ) : null}
          {done && !garment ? <Text style={styles.meta}>{item.name}</Text> : null}
          {status.step ? <Text style={styles.meta}>{status.step}</Text> : null}
          {hasBar ? (
            <ProgressBar value={status.progress} label={`Progreso de ${item.name}`} />
          ) : null}
          {item.lowRes ? (
            <Text style={styles.warning} testID="low-res-note">
              {LOW_RES_NOTE}
            </Text>
          ) : null}
        </View>
      </View>
      {footer}
    </Card>
  );
}

/** Local preview while uploading and analysing; the cutout on its tint once it exists. */
function Thumb({
  item,
  garment,
  scanning,
}: {
  item: QueueItem;
  garment?: Garment;
  scanning: boolean;
}) {
  const cutout = imageUrl(garment?.img_cutout ?? garment?.img_thumb);
  const dominant = garment?.colors?.[0]?.hex;
  return (
    <View
      style={[styles.thumb, { backgroundColor: dominant ? tint(dominant) : colors.surface2 }]}
      testID="upload-thumb"
    >
      {cutout ? (
        <GarmentImage uri={cutout} tintColor={dominant} />
      ) : item.previewUri ? (
        <Image
          source={{ uri: item.previewUri }}
          style={StyleSheet.absoluteFill}
          contentFit="cover"
          accessibilityLabel={`Vista previa de ${item.name}`}
        />
      ) : null}
      {scanning ? <ScanLine /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { padding: 12, gap: 12 },
  row: { flexDirection: 'row', gap: 14 },
  thumb: { width: 84, height: 105, borderRadius: radii.tile, overflow: 'hidden' },
  body: { flex: 1, gap: 6, justifyContent: 'center' },
  head: { gap: 6, alignItems: 'flex-start' },
  name: {
    fontFamily: fontFamilies.bodySemiBold,
    fontSize: 14.5,
    lineHeight: 20,
    color: colors.ink,
  },
  details: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 10 },
  meta: { fontFamily: fontFamilies.body, fontSize: 13, lineHeight: 18, color: colors.ink2 },
  confidence: { fontFamily: fontFamilies.bodyMedium, fontSize: 12.5, color: colors.okText },
  warning: { fontFamily: fontFamilies.body, fontSize: 13, lineHeight: 18, color: colors.warnText },
  error: { fontFamily: fontFamilies.body, fontSize: 13, lineHeight: 18, color: colors.danger },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
});
