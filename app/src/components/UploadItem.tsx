import { useRouter } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useRetryGarment } from '@/hooks/useGarmentMutations';
import { useJob } from '@/hooks/useJob';
import type { QueueItem } from '@/hooks/useUploadQueue';

const STEP_LABELS: Record<string, string> = {
  preprocess: 'Preparando',
  cutout: 'Recortando',
  color: 'Analizando colores',
  ai_attributes: 'Analizando prenda',
  embedding: 'Calculando similitud',
  consolidate: 'Terminando',
};

type UploadItemProps = {
  item: QueueItem;
  onRetryUpload: (key: string) => void;
  onDismiss: (key: string) => void;
};

/** One photo on Añadir with its own progress bar (UI-REQ-006/018/019). */
export function UploadItem({ item, onRetryUpload, onDismiss }: UploadItemProps) {
  if (item.phase === 'queued' && item.jobId && item.garmentId) {
    return <ProcessingItem item={item} jobId={item.jobId} garmentId={item.garmentId} />;
  }

  const failed = item.phase === 'error';
  return (
    <View style={styles.card} testID={`upload-item-${item.key}`}>
      <Text style={styles.name}>{item.name}</Text>
      {failed ? (
        <>
          <Text style={styles.error}>{item.error}</Text>
          <View style={styles.actions}>
            {item.photo ? (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`Reintentar subida de ${item.name}`}
                onPress={() => onRetryUpload(item.key)}
                style={styles.button}
              >
                <Text style={styles.buttonText}>Reintentar</Text>
              </Pressable>
            ) : null}
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`Quitar ${item.name}`}
              onPress={() => onDismiss(item.key)}
              style={styles.secondary}
            >
              <Text style={styles.secondaryText}>Quitar</Text>
            </Pressable>
          </View>
        </>
      ) : (
        <>
          <Text style={styles.status}>
            {item.phase === 'preparing' ? 'Preparando foto' : 'Subiendo'}
          </Text>
          <ProgressBar value={0} />
        </>
      )}
    </View>
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

  let status = 'En cola';
  if (data?.status === 'done') {
    status = 'Listo';
  } else if (data?.status === 'failed') {
    status = 'Falló';
  } else if (data?.step) {
    status = STEP_LABELS[data.step] ?? 'Procesando';
  }

  return (
    <View style={styles.card} testID={`upload-item-${item.key}`}>
      <Text style={styles.name}>{item.name}</Text>
      <Text style={styles.status}>{status}</Text>
      {data?.status === 'failed' ? (
        <>
          <Text style={styles.error}>{data.error ?? 'No se pudo procesar la foto.'}</Text>
          {retry.error ? <Text style={styles.error}>{retry.error.message}</Text> : null}
          <View style={styles.actions}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`Reintentar ${item.name}`}
              onPress={() => retry.mutate()}
              disabled={retry.isPending}
              style={styles.button}
            >
              <Text style={styles.buttonText}>Reintentar</Text>
            </Pressable>
          </View>
        </>
      ) : (
        <ProgressBar value={data?.status === 'done' ? 100 : (data?.progress ?? 0)} />
      )}
      {job.isError ? <Text style={styles.error}>{job.error.message}</Text> : null}
      {data?.status === 'done' ? (
        <View style={styles.actions}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Revisar ${item.name}`}
            onPress={() => router.push(`/review/${garmentId}`)}
            style={styles.button}
          >
            <Text style={styles.buttonText}>Revisar</Text>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

function ProgressBar({ value }: { value: number }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <View
      accessible
      style={styles.track}
      accessibilityRole="progressbar"
      accessibilityValue={{ min: 0, max: 100, now: clamped }}
    >
      <View style={[styles.fill, { width: `${clamped}%` }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  card: { padding: 12, borderRadius: 10, borderWidth: 1, borderColor: '#d0d5dd', gap: 8 },
  name: { fontSize: 15, fontWeight: '600' },
  status: { fontSize: 13, opacity: 0.7 },
  error: { fontSize: 13, color: '#b42318' },
  track: { height: 6, borderRadius: 3, backgroundColor: '#e4e7ec', overflow: 'hidden' },
  fill: { height: 6, backgroundColor: '#208AEF' },
  actions: { flexDirection: 'row', gap: 8 },
  button: {
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: 8,
    backgroundColor: '#208AEF',
  },
  buttonText: { color: '#fff', fontWeight: '600' },
  secondary: {
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#d0d5dd',
  },
  secondaryText: { fontWeight: '600' },
});
