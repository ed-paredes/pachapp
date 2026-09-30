import { useQueryClient } from '@tanstack/react-query';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '@/api-client/errors';
import { queryKeys } from '@/api-client/query-keys';
import { HeroImage } from '@/components/GarmentImage';
import { centeredContentStyle } from '@/components/ContentContainer';
import type { components } from '@/api-client/schema';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { LoadingState } from '@/components/LoadingState';
import {
  useArchiveGarment,
  useDeleteGarment,
  usePatchGarment,
  useReactivateGarment,
  useRetryGarment,
} from '@/hooks/useGarmentMutations';
import { useGarment } from '@/hooks/useGarments';
import { useJob } from '@/hooks/useJob';
import { imageUrl } from '@/lib/image-url';
import {
  categoryLabel,
  PATTERN_LABELS,
  SEASON_LABELS,
  STATUS_LABELS,
  STYLE_LABELS,
} from '@/lib/labels';

type Garment = components['schemas']['GarmentDetail'];

const STEP_LABELS: Record<string, string> = {
  preprocess: 'Preparando',
  cutout: 'Recortando',
  color: 'Analizando colores',
  ai_attributes: 'Analizando prenda',
  embedding: 'Calculando similitud',
  consolidate: 'Terminando',
};
const ACTIVE_JOB = ['pending', 'claimed', 'running'];
const ACTION_ERROR = 'No se pudo completar la acción. Inténtalo de nuevo.';

function lookup<T extends string>(labels: Record<T, string>, key: string): string {
  return labels[key as T] ?? key;
}

function formatDate(iso: string | null): string {
  if (!iso) return 'Nunca';
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString('es-ES');
}

/**
 * Detalle de prenda (GarmentDetail): cutout, read-only attributes, usage and
 * the status actions (UI-REQ-016). Editing lives in Revisión.
 */
export default function GarmentDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const garment = useGarment(id);

  if (garment.isPending) {
    return <LoadingState />;
  }
  if (garment.isError && !garment.data) {
    if (garment.error instanceof ApiError && garment.error.status === 404) {
      return (
        <EmptyState
          title="No encontramos esta prenda"
          description="Puede que se haya eliminado. Vuelve al armario."
        />
      );
    }
    return <ErrorState message={garment.error.message} onRetry={() => void garment.refetch()} />;
  }
  return <Detail garment={garment.data as Garment} />;
}

function Detail({ garment }: { garment: Garment }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const id = garment.id;
  const patch = usePatchGarment(id);
  const archive = useArchiveGarment(id);
  const reactivate = useReactivateGarment(id);
  const retry = useRetryGarment(id);
  const remove = useDeleteGarment(id);
  const [confirming, setConfirming] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const jobId = garment.job?.id;
  const processing = !!garment.job && ACTIVE_JOB.includes(garment.job.status);
  const jobQuery = useJob(jobId, { enabled: processing });
  const liveJob = jobQuery.data ?? garment.job;
  const failed = garment.job?.status === 'failed';

  // The job finished while the detail still shows it as running: refresh the garment.
  const liveStatus = jobQuery.data?.status;
  useEffect(() => {
    if (processing && (liveStatus === 'done' || liveStatus === 'failed')) {
      void queryClient.invalidateQueries({ queryKey: queryKeys.garments.detail(id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.garments.lists() });
    }
  }, [processing, liveStatus, queryClient, id]);

  const run = async (action: () => Promise<unknown>) => {
    setActionError(null);
    try {
      await action();
    } catch (error) {
      setActionError(error instanceof ApiError ? error.message : ACTION_ERROR);
    }
  };

  const confirmDelete = async () => {
    setActionError(null);
    try {
      await remove.mutateAsync();
      router.replace('/(tabs)/wardrobe');
    } catch (error) {
      setConfirming(false);
      setActionError(error instanceof ApiError ? error.message : ACTION_ERROR);
    }
  };

  const uri = imageUrl(garment.img_cutout) ?? imageUrl(garment.img_thumb);
  const progress = Math.max(0, Math.min(100, liveJob?.progress ?? 0));

  return (
    <ScrollView contentContainerStyle={[styles.container, centeredContentStyle]}>
      {uri ? <HeroImage uri={uri} testID="detail-image" /> : null}

      {processing ? (
        <View testID="detail-processing" style={styles.notice}>
          <Text style={styles.noticeTitle}>Procesando…</Text>
          {liveJob?.step ? (
            <Text style={styles.muted}>{STEP_LABELS[liveJob.step] ?? liveJob.step}</Text>
          ) : null}
          <View
            accessible
            style={styles.track}
            accessibilityRole="progressbar"
            accessibilityValue={{ min: 0, max: 100, now: progress }}
          >
            <View style={[styles.fill, { width: `${progress}%` }]} />
          </View>
        </View>
      ) : null}

      {failed ? (
        <View testID="detail-failed" style={styles.notice}>
          <Text style={styles.noticeTitle}>Falló el procesamiento</Text>
          {garment.job?.error ? <Text style={styles.muted}>{garment.job.error}</Text> : null}
          <ActionButton
            label="Reintentar procesamiento"
            disabled={retry.isPending}
            onPress={() => void run(() => retry.mutateAsync())}
          />
        </View>
      ) : null}

      <View style={styles.titleRow}>
        <Text style={styles.title}>{categoryLabel(garment.category)}</Text>
        <Text style={styles.status} testID="detail-status">
          {STATUS_LABELS[garment.status]}
        </Text>
        {garment.needs_review ? (
          <View style={styles.badge} testID="review-badge">
            <Text style={styles.badgeText}>Revisar</Text>
          </View>
        ) : null}
      </View>

      <Section title="Atributos">
        <Row label="Subcategoría" value={garment.subcategory} />
        <View style={styles.row}>
          <Text style={styles.rowLabel}>Colores</Text>
          <View style={styles.swatches} testID="detail-colors">
            {garment.colors?.length ? (
              garment.colors.map((entry) => (
                <View key={entry.name} style={styles.swatch}>
                  <View style={[styles.dot, { backgroundColor: entry.hex }]} />
                  <Text style={styles.value}>{entry.name}</Text>
                </View>
              ))
            ) : (
              <Text style={styles.value}>Sin definir</Text>
            )}
          </View>
        </View>
        <Row label="Estampado" value={garment.pattern ? PATTERN_LABELS[garment.pattern] : null} />
        <Row label="Formalidad" value={garment.formality} />
        <Row
          label="Estilos"
          value={garment.style_tags?.map((tag) => lookup(STYLE_LABELS, tag)).join(', ')}
        />
        <Row
          label="Temporadas"
          value={garment.seasons?.map((season) => lookup(SEASON_LABELS, season)).join(', ')}
        />
        <Row label="Abrigo" value={garment.warmth} />
        <Row label="Material" value={garment.material} />
        <Row label="Marca" value={garment.brand} />
        <Row label="Notas" value={garment.notes} />
      </Section>

      <Section title="Uso">
        <Row label="Veces puesta" value={garment.wear_count} />
        <Row label="Última vez" value={formatDate(garment.last_worn_at)} />
        <Row label="Outfits" value={garment.outfit_count} />
      </Section>

      {actionError ? (
        <Text style={styles.error} testID="action-error">
          {actionError}
        </Text>
      ) : null}

      <View style={styles.actions}>
        <ActionButton label="Revisar" onPress={() => router.push(`/review/${id}`)} />
        {garment.status === 'active' ? (
          <ActionButton
            label="Marcar como lavando"
            disabled={patch.isPending}
            onPress={() => void run(() => patch.mutateAsync({ status: 'laundry' }))}
          />
        ) : null}
        {garment.status === 'laundry' ? (
          <ActionButton
            label="Marcar como activa"
            disabled={patch.isPending}
            onPress={() => void run(() => patch.mutateAsync({ status: 'active' }))}
          />
        ) : null}
        {garment.status === 'archived' ? (
          <ActionButton
            label="Reactivar"
            disabled={reactivate.isPending}
            onPress={() => void run(() => reactivate.mutateAsync())}
          />
        ) : (
          <ActionButton
            label="Archivar"
            disabled={archive.isPending}
            onPress={() => void run(() => archive.mutateAsync())}
          />
        )}
        <ActionButton label="Eliminar" destructive onPress={() => setConfirming(true)} />
      </View>

      {confirming ? (
        <View style={styles.confirm} testID="delete-confirm">
          <Text style={styles.noticeTitle}>¿Eliminar esta prenda?</Text>
          <Text style={styles.muted}>Esta acción no se puede deshacer.</Text>
          <ActionButton label="Cancelar" onPress={() => setConfirming(false)} />
          <ActionButton
            label="Eliminar definitivamente"
            destructive
            disabled={remove.isPending}
            onPress={() => void confirmDelete()}
          />
        </View>
      ) : null}
    </ScrollView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function Row({ label, value }: { label: string; value: string | number | null | undefined }) {
  const empty = value === null || value === undefined || value === '';
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.value}>{empty ? 'Sin definir' : String(value)}</Text>
    </View>
  );
}

function ActionButton({
  label,
  onPress,
  destructive,
  disabled,
}: {
  label: string;
  onPress: () => void;
  destructive?: boolean;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: !!disabled }}
      disabled={disabled}
      onPress={onPress}
      style={[styles.button, destructive && styles.buttonDestructive, disabled && styles.disabled]}
    >
      <Text style={[styles.buttonText, destructive && styles.buttonTextDestructive]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16, gap: 12 },
  notice: { gap: 8, padding: 12, borderRadius: 10, backgroundColor: '#F8FAFC' },
  noticeTitle: { fontSize: 15, fontWeight: '600' },
  muted: { fontSize: 13, opacity: 0.7 },
  track: { height: 6, borderRadius: 3, backgroundColor: '#E4E7EC', overflow: 'hidden' },
  fill: { height: 6, backgroundColor: '#208AEF' },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' },
  title: { fontSize: 22, fontWeight: '700' },
  status: { fontSize: 13, fontWeight: '600', opacity: 0.7 },
  badge: {
    paddingVertical: 2,
    paddingHorizontal: 8,
    borderRadius: 10,
    backgroundColor: '#F79009',
  },
  badgeText: { color: '#fff', fontSize: 12, fontWeight: '700' },
  section: { gap: 6 },
  sectionTitle: { fontSize: 16, fontWeight: '700', marginTop: 4 },
  row: { flexDirection: 'row', justifyContent: 'space-between', gap: 12 },
  rowLabel: { fontSize: 14, opacity: 0.7 },
  value: { fontSize: 14, flexShrink: 1, textAlign: 'right' },
  swatches: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    justifyContent: 'flex-end',
    flex: 1,
  },
  swatch: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  dot: { width: 16, height: 16, borderRadius: 8, borderWidth: 1, borderColor: '#D0D5DD' },
  actions: { gap: 8, marginTop: 8 },
  button: {
    paddingVertical: 12,
    borderRadius: 10,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#208AEF',
  },
  buttonDestructive: { borderColor: '#B42318' },
  disabled: { opacity: 0.5 },
  buttonText: { fontSize: 15, fontWeight: '600', color: '#208AEF' },
  buttonTextDestructive: { color: '#B42318' },
  confirm: { gap: 8, padding: 12, borderRadius: 10, backgroundColor: '#FEF3F2' },
  error: { fontSize: 13, color: '#B42318' },
});
