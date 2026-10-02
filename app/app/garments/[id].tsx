import { useQueryClient } from '@tanstack/react-query';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useState, type ReactNode } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
  type ViewStyle,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ApiError } from '@/api-client/errors';
import { queryKeys } from '@/api-client/query-keys';
import type { components } from '@/api-client/schema';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { BackButton, GarmentHero } from '@/components/GarmentHero';
import { IconSymbol } from '@/components/IconSymbol';
import { LoadingState } from '@/components/LoadingState';
import {
  AddChip,
  Button,
  Card,
  ColorSwatch,
  Eyebrow,
  FormalityMeter,
  Pill,
  SeasonPicker,
  StatRow,
  Title,
  useToast,
} from '@/components/ui';
import { pressFeedback } from '@/components/ui/feedback';
import type { IconName } from '@/components/ui/icons';
import {
  useArchiveGarment,
  useDeleteGarment,
  usePatchGarment,
  useReactivateGarment,
  useRetryGarment,
} from '@/hooks/useGarmentMutations';
import { useGarment } from '@/hooks/useGarments';
import { useJob } from '@/hooks/useJob';
import { formatLastWorn } from '@/lib/format-date';
import { garmentName } from '@/lib/garment-name';
import { imageUrl } from '@/lib/image-url';
import { categoryLabel, PATTERN_LABELS, STYLE_LABELS } from '@/lib/labels';
import {
  CONTENT_MAX_WIDTH,
  TWO_COLUMNS,
  colors,
  fontFamilies,
  radii,
  shadows,
  spacing,
  textStyles,
} from '@/theme';

type Garment = components['schemas']['GarmentDetail'];
type SeasonValue = components['schemas']['Season'];

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
/** Tint of the hero when the garment has no colour yet. */
const NEUTRAL_HERO = '#A39A8E';

const ICONS = {
  review: { ios: 'pencil', android: 'edit', web: 'edit' },
  laundry: { ios: 'drop', android: 'water_drop', web: 'water_drop' },
  activate: { ios: 'checkmark.circle', android: 'check_circle', web: 'check_circle' },
  archive: { ios: 'archivebox', android: 'archive', web: 'archive' },
  unarchive: { ios: 'arrow.uturn.backward', android: 'unarchive', web: 'unarchive' },
} satisfies Record<string, IconName>;

function lookup<T extends string>(labels: Record<T, string>, key: string): string {
  return labels[key as T] ?? key;
}

/** Back to where the user came from; Armario when the page was opened directly. */
function useGoBack() {
  const router = useRouter();
  return () => (router.canGoBack() ? router.back() : router.replace('/(tabs)/wardrobe'));
}

/**
 * Detalle de prenda (GarmentDetail): cutout hero, usage, read-only attributes and the status
 * actions (UI-REQ-016). Editing lives in Revisión.
 */
export default function GarmentDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const garment = useGarment(id);

  if (garment.isPending) {
    return <StateShell state={<LoadingState />} />;
  }
  if (garment.isError && !garment.data) {
    if (garment.error instanceof ApiError && garment.error.status === 404) {
      return (
        <StateShell
          state={
            <EmptyState
              title="No encontramos esta prenda"
              description="Puede que se haya eliminado. Vuelve al armario."
            />
          }
        />
      );
    }
    return (
      <StateShell
        state={
          <ErrorState message={garment.error.message} onRetry={() => void garment.refetch()} />
        }
      />
    );
  }
  return <Detail garment={garment.data as Garment} />;
}

/** Loading / error / not-found: the stack header is hidden, so these keep a way back. */
function StateShell({ state }: { state: ReactNode }) {
  const goBack = useGoBack();
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.shell, { paddingTop: insets.top + spacing.md }]}>
      <View style={styles.shellBack}>
        <BackButton onPress={goBack} />
      </View>
      {state}
    </View>
  );
}

function Detail({ garment }: { garment: Garment }) {
  const router = useRouter();
  const goBack = useGoBack();
  const toast = useToast();
  const queryClient = useQueryClient();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const twoColumns = width >= TWO_COLUMNS;
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

  const run = async (action: () => Promise<unknown>, success?: string) => {
    setActionError(null);
    try {
      await action();
      if (success) toast.show(success);
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
  const edit = () => router.push(`/review/${id}`);
  const hero = (
    <GarmentHero
      uri={uri}
      color={garment.colors?.[0]?.hex ?? NEUTRAL_HERO}
      onBack={goBack}
      analyzed={!!garment.img_cutout && !processing && !failed}
      sticky={twoColumns}
      testID="detail-image"
    />
  );

  const details = (
    <View style={styles.details}>
      <View style={styles.head}>
        <Eyebrow>{categoryLabel(garment.category)}</Eyebrow>
        <Title>{garmentName(garment)}</Title>
        <View style={styles.pills}>
          <StatusPill status={garment.status} />
          {garment.needs_review ? (
            <Pill label="Pendiente de revisión" tone="warn" testID="review-badge" />
          ) : null}
        </View>
      </View>

      {processing ? (
        <Card style={styles.notice} testID="detail-processing">
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
        </Card>
      ) : null}

      {failed ? (
        <Card style={styles.notice} testID="detail-failed">
          <Text style={styles.noticeTitle}>Falló el procesamiento</Text>
          {garment.job?.error ? <Text style={styles.muted}>{garment.job.error}</Text> : null}
          <Button
            label="Reintentar procesamiento"
            variant="secondary"
            disabled={retry.isPending}
            onPress={() => void run(() => retry.mutateAsync())}
          />
        </Card>
      ) : null}

      <Card>
        <StatRow
          stats={[
            { value: String(garment.wear_count), label: 'veces puesta' },
            { value: formatLastWorn(garment.last_worn_at), label: 'última vez' },
            { value: String(garment.outfit_count), label: 'outfits' },
          ]}
        />
      </Card>
      {/* "Crear outfit con esta prenda" is not shown: the outfit engine does not exist yet. */}

      <Attributes garment={garment} onEdit={edit} />

      {actionError ? (
        <Text style={styles.error} testID="action-error" accessibilityRole="alert">
          {actionError}
        </Text>
      ) : null}

      <View style={styles.actions}>
        <ActionTile icon={ICONS.review} label="Revisar" onPress={edit} />
        {garment.status === 'laundry' ? (
          <ActionTile
            icon={ICONS.activate}
            label="Marcar como activa"
            disabled={patch.isPending}
            onPress={() =>
              void run(() => patch.mutateAsync({ status: 'active' }), 'Marcada como activa')
            }
          />
        ) : garment.status === 'active' ? (
          <ActionTile
            icon={ICONS.laundry}
            label="A lavar"
            accessibilityLabel="Marcar como lavando"
            disabled={patch.isPending}
            onPress={() =>
              void run(() => patch.mutateAsync({ status: 'laundry' }), 'Marcada como lavando')
            }
          />
        ) : null}
        {garment.status === 'archived' ? (
          <ActionTile
            icon={ICONS.unarchive}
            label="Reactivar"
            disabled={reactivate.isPending}
            onPress={() => void run(() => reactivate.mutateAsync(), 'Prenda reactivada')}
          />
        ) : (
          <ActionTile
            icon={ICONS.archive}
            label="Archivar"
            disabled={archive.isPending}
            onPress={() => void run(() => archive.mutateAsync(), 'Prenda archivada')}
          />
        )}
      </View>

      {confirming ? (
        <View style={styles.confirm} testID="delete-confirm">
          <Text style={styles.noticeTitle}>¿Eliminar esta prenda?</Text>
          <Text style={styles.muted}>Esta acción no se puede deshacer.</Text>
          <View style={styles.confirmActions}>
            <Button label="Cancelar" variant="secondary" onPress={() => setConfirming(false)} />
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Eliminar definitivamente"
              accessibilityState={{ disabled: remove.isPending }}
              disabled={remove.isPending}
              onPress={() => void confirmDelete()}
              style={(state) => [
                styles.danger,
                remove.isPending && styles.disabled,
                pressFeedback(state),
              ]}
            >
              <Text style={styles.dangerText}>Eliminar definitivamente</Text>
            </Pressable>
          </View>
        </View>
      ) : (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Eliminar prenda"
          onPress={() => setConfirming(true)}
          style={styles.deleteLink}
        >
          <Text style={styles.deleteText}>Eliminar prenda</Text>
        </Pressable>
      )}
    </View>
  );

  return (
    <ScrollView
      style={styles.root}
      contentContainerStyle={[
        styles.content,
        {
          paddingTop: insets.top + (twoColumns ? spacing.xxl : spacing.md),
          paddingBottom: insets.bottom + spacing.xxl,
        },
      ]}
    >
      <View testID="detail-page" style={[styles.page, twoColumns && styles.pageTwo]}>
        <View style={twoColumns ? styles.column : undefined}>{hero}</View>
        <View style={twoColumns ? styles.column : undefined}>{details}</View>
      </View>
    </ScrollView>
  );
}

function StatusPill({ status }: { status: Garment['status'] }) {
  if (status === 'laundry') return <Pill label="Lavando" tone="info" dot testID="detail-status" />;
  if (status === 'archived') return <Pill label="Archivada" tone="ghost" testID="detail-status" />;
  return <Pill label="En el armario" tone="ok" dot testID="detail-status" />;
}

/** Read-only attributes; empty ones are an "+ Añadir" chip that opens Revisión. */
function Attributes({ garment, onEdit }: { garment: Garment; onEdit: () => void }) {
  const add = (what: string) => <AddChip accessibilityLabel={`Añadir ${what}`} onPress={onEdit} />;
  const tags = (values: string[]) => (
    <View style={styles.chips}>
      {values.map((value) => (
        <View key={value} style={styles.tag}>
          <Text style={styles.tagText}>{value}</Text>
        </View>
      ))}
    </View>
  );
  const text = (value: string | number | null | undefined, what: string) =>
    value === null || value === undefined || value === '' ? add(what) : tags([String(value)]);

  return (
    <Card style={styles.attrs}>
      <View style={styles.attrsHead}>
        <Text style={styles.attrsTitle}>Atributos</Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Editar atributos"
          onPress={onEdit}
          style={(state) => [styles.editLink, pressFeedback(state)]}
        >
          <Text style={styles.editText}>Editar</Text>
        </Pressable>
      </View>
      <AttrRow label="Colores" first>
        {garment.colors?.length ? (
          <View style={styles.chips} testID="detail-colors">
            {garment.colors.map((entry) => (
              <ColorSwatch key={entry.name} color={entry.hex} label={entry.name} />
            ))}
          </View>
        ) : (
          add('colores')
        )}
      </AttrRow>
      <AttrRow label="Estilo">
        {garment.style_tags?.length
          ? tags(garment.style_tags.map((tag) => lookup(STYLE_LABELS, tag)))
          : add('estilo')}
      </AttrRow>
      <AttrRow label="Formalidad">
        {garment.formality ? <FormalityMeter level={garment.formality} /> : add('formalidad')}
      </AttrRow>
      <AttrRow label="Temporada">
        {garment.seasons?.length ? (
          <SeasonPicker value={garment.seasons as SeasonValue[]} />
        ) : (
          add('temporada')
        )}
      </AttrRow>
      <AttrRow label="Estampado">
        {text(garment.pattern ? PATTERN_LABELS[garment.pattern] : null, 'estampado')}
      </AttrRow>
      <AttrRow label="Material">{text(garment.material, 'material')}</AttrRow>
      <AttrRow label="Abrigo">
        {text(garment.warmth ? `${garment.warmth} de 5` : null, 'abrigo')}
      </AttrRow>
      <AttrRow label="Marca">{text(garment.brand, 'marca')}</AttrRow>
      <AttrRow label="Notas">
        {garment.notes ? <Text style={styles.notes}>{garment.notes}</Text> : add('notas')}
      </AttrRow>
    </Card>
  );
}

function AttrRow({
  label,
  children,
  first,
}: {
  label: string;
  children: ReactNode;
  first?: boolean;
}) {
  return (
    <View style={[styles.attrRow, !first && styles.attrRowBorder]}>
      <Text style={styles.attrLabel}>{label}</Text>
      <View style={styles.attrValue}>{children}</View>
    </View>
  );
}

function ActionTile({
  icon,
  label,
  accessibilityLabel,
  onPress,
  disabled,
}: {
  icon: IconName;
  label: string;
  accessibilityLabel?: string;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityState={{ disabled: !!disabled }}
      disabled={disabled}
      onPress={onPress}
      style={(state) => [styles.tile, disabled && styles.disabled, pressFeedback(state)]}
    >
      <IconSymbol name={icon} size={22} color={colors.ink2} />
      <Text style={styles.tileLabel}>{label}</Text>
    </Pressable>
  );
}

const centered: ViewStyle = { width: '100%', maxWidth: CONTENT_MAX_WIDTH, alignSelf: 'center' };

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  content: { ...centered, paddingHorizontal: spacing.screen },
  shell: { flex: 1, backgroundColor: colors.bg, paddingHorizontal: spacing.screen },
  shellBack: { alignItems: 'flex-start' },
  page: { gap: spacing.xxl },
  pageTwo: { flexDirection: 'row', alignItems: 'stretch' },
  column: { flex: 1 },
  details: { gap: spacing.lg },
  head: { gap: 6 },
  pills: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 },
  notice: { gap: 8, padding: spacing.lg },
  noticeTitle: { ...textStyles.body, fontFamily: fontFamilies.bodySemiBold, color: colors.ink },
  muted: { fontFamily: fontFamilies.body, fontSize: 13.5, lineHeight: 20, color: colors.ink2 },
  track: { height: 6, borderRadius: 3, backgroundColor: colors.surface3, overflow: 'hidden' },
  fill: { height: 6, backgroundColor: colors.accent },
  attrs: { padding: spacing.xl },
  attrsHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  attrsTitle: { fontFamily: fontFamilies.display, fontSize: 18, color: colors.ink },
  editLink: { minHeight: 44, minWidth: 44, justifyContent: 'center', alignItems: 'flex-end' },
  editText: { fontFamily: fontFamilies.bodyMedium, fontSize: 13.5, color: colors.accentText },
  attrRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10 },
  attrRowBorder: { borderTopWidth: 1, borderTopColor: colors.line },
  attrLabel: { width: 96, fontFamily: fontFamilies.body, fontSize: 13, color: colors.ink2 },
  attrValue: { flex: 1, alignItems: 'flex-start' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  tag: {
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: radii.pill,
    backgroundColor: colors.surface2,
  },
  tagText: { fontFamily: fontFamilies.bodyMedium, fontSize: 13, color: colors.ink },
  notes: { fontFamily: fontFamilies.body, fontSize: 14, lineHeight: 20, color: colors.ink },
  error: { fontFamily: fontFamilies.body, fontSize: 13.5, color: colors.danger },
  actions: { flexDirection: 'row', gap: 8 },
  tile: {
    flex: 1,
    minHeight: 76,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 14,
    paddingHorizontal: 6,
    borderRadius: radii.sm,
    backgroundColor: colors.surface,
    boxShadow: shadows.card,
  },
  tileLabel: {
    fontFamily: fontFamilies.bodyMedium,
    fontSize: 12.5,
    color: colors.ink2,
    textAlign: 'center',
  },
  disabled: { opacity: 0.5 },
  deleteLink: {
    alignSelf: 'center',
    minHeight: 44,
    justifyContent: 'center',
    paddingHorizontal: 16,
  },
  deleteText: { fontFamily: fontFamilies.bodyMedium, fontSize: 13.5, color: colors.danger },
  confirm: {
    gap: 10,
    padding: spacing.lg,
    borderRadius: radii.md,
    backgroundColor: colors.dangerSoft,
  },
  confirmActions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  danger: {
    minHeight: 44,
    justifyContent: 'center',
    paddingHorizontal: 22,
    borderRadius: radii.pill,
    backgroundColor: colors.danger,
  },
  dangerText: { fontFamily: fontFamilies.bodySemiBold, fontSize: 15, color: colors.onInk },
});
