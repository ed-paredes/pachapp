import { useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import { useState } from 'react';
import {
  FlatList,
  RefreshControl,
  ScrollView,
  StyleSheet,
  useWindowDimensions,
  View,
} from 'react-native';

import { queryKeys, type GarmentFilters } from '@/api-client/query-keys';
import type { components } from '@/api-client/schema';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { AddGarmentTile, GarmentCard } from '@/components/GarmentCard';
import { LoadingState } from '@/components/LoadingState';
import {
  Banner,
  Button,
  Eyebrow,
  FilterChip,
  Screen,
  Segmented,
  type SegmentedOption,
  Title,
} from '@/components/ui';
import { useIsOffline } from '@/offline/reachability';
import { flattenGarmentPages, useGarments, useInfiniteGarments } from '@/hooks/useGarments';
import { CATEGORY_LABELS, CATEGORY_ORDER } from '@/lib/labels';
import { CONTENT_MAX_WIDTH, gridColumns, spacing } from '@/theme';

type Category = components['schemas']['GarmentCategory'];
type GarmentStatus = components['schemas']['GarmentStatus'];
type CountFilters = Pick<GarmentFilters, 'status' | 'category' | 'needs_review'>;

const PAGE_SIZE = 50;
const GAP = spacing.md;
const DEFAULT_STATUS: GarmentStatus[] = ['active', 'laundry'];

/**
 * `null` = default view: active + laundry together (UI-REQ-004). No segment is highlighted
 * then, because "Activas" means active only (the mockup's default segment) and the default is
 * wider than that; pressing the highlighted segment again returns to it.
 */
type StatusChoice = GarmentStatus | 'all' | null;
type SegmentValue = Exclude<StatusChoice, null>;

const STATUS_SEGMENTS: { value: SegmentValue; label: string }[] = [
  { value: 'active', label: 'Activas' },
  { value: 'laundry', label: 'Lavando' },
  { value: 'archived', label: 'Archivadas' },
  { value: 'all', label: 'Todas' },
];

function statusFilter(choice: StatusChoice): GarmentStatus[] {
  if (choice === null) return DEFAULT_STATUS;
  if (choice === 'all') return ['active', 'laundry', 'archived'];
  return [choice];
}

/** Total of a list query: one cheap request (page size 1) per counter. */
function useTotal(filters: CountFilters): number | undefined {
  return useGarments({ ...filters, page_size: 1 }).data?.total;
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

const ADD_TILE_ID = '__add__';

/**
 * Armario (Wardrobe): garments as cutouts on their own colour, filtered by category and
 * state, with a banner for the ones pending review (UI-REQ-004, UI-REQ-008).
 */
export default function WardrobeScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { width } = useWindowDimensions();
  // Columns come from the content width (capped like the container) and a minimum card width.
  const contentWidth = Math.min(width, CONTENT_MAX_WIDTH) - spacing.screen * 2;
  const columns = gridColumns(contentWidth, undefined, GAP);
  const cardWidth = Math.floor((contentWidth - GAP * (columns - 1)) / columns);

  const [category, setCategory] = useState<Category | null>(null);
  const [statusChoice, setStatusChoice] = useState<StatusChoice>(null);
  const [needsReview, setNeedsReview] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const status = statusFilter(statusChoice);
  const filters: Omit<GarmentFilters, 'page'> = {
    status,
    sort: 'created_at',
    order: 'desc',
    page_size: PAGE_SIZE,
    ...(category ? { category } : {}),
    ...(needsReview ? { needs_review: true } : {}),
  };
  const query = useInfiniteGarments(filters);
  const filtered = category !== null || statusChoice !== null || needsReview;
  const items = flattenGarmentPages(query.data?.pages);
  // A failed next page / refresh / background poll after the first page loaded.
  // Offline the banner already says so, so a failed refresh adds no second warning.
  const offline = useIsOffline();
  const softError = query.isError && query.data && !offline ? query.error : null;

  // Eyebrow numbers, status counters (scoped to the category) and the review banner.
  const review = needsReview ? undefined : { needs_review: true as const };
  const wardrobeTotal = useTotal({ status: DEFAULT_STATUS });
  const activeTotal = useTotal({ status: ['active'] });
  const scope = {
    ...(category ? { category } : {}),
    ...(needsReview ? { needs_review: true } : {}),
  };
  const counts: Record<SegmentValue, number | undefined> = {
    active: useTotal({ ...scope, status: ['active'] }),
    laundry: useTotal({ ...scope, status: ['laundry'] }),
    archived: useTotal({ ...scope, status: ['archived'] }),
    all: useTotal({ ...scope, status: statusFilter('all') }),
  };
  const reviewQuery = useGarments({ status: DEFAULT_STATUS, ...review, page_size: 1 });
  const pendingReview = needsReview ? 0 : (reviewQuery.data?.total ?? 0);

  const clearFilters = () => {
    setCategory(null);
    setStatusChoice(null);
    setNeedsReview(false);
  };
  const openReview = () => {
    const only = reviewQuery.data?.items[0];
    if (pendingReview === 1 && only) {
      router.push(`/review/${only.id}`);
      return;
    }
    // Several garments: list them in the grid, with a removable "Pendientes de revisión" chip.
    setCategory(null);
    setStatusChoice(null);
    setNeedsReview(true);
  };
  const retrySoftError = () => {
    if (query.isFetchNextPageError) void query.fetchNextPage();
    else void query.refetch();
  };
  const refresh = async () => {
    setRefreshing(true);
    try {
      // Every active garment list: the grid plus the counters and the review banner.
      await queryClient.refetchQueries({ queryKey: queryKeys.garments.lists(), type: 'active' });
    } finally {
      setRefreshing(false);
    }
  };

  const segmentOptions: SegmentedOption<SegmentValue>[] = STATUS_SEGMENTS.map((segment) => ({
    ...segment,
    count: counts[segment.value],
  }));

  const header = (
    <View style={styles.header}>
      <View style={styles.titleBlock}>
        {wardrobeTotal !== undefined && activeTotal !== undefined ? (
          <Eyebrow>{`${plural(wardrobeTotal, 'prenda', 'prendas')} · ${plural(activeTotal, 'activa', 'activas')}`}</Eyebrow>
        ) : null}
        <Title>Tu armario</Title>
        {/* No search box: the API has no text search yet. */}
      </View>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.row}
        contentContainerStyle={styles.chips}
      >
        <CategoryChip
          label="Todas"
          selected={category === null}
          filters={{ status, ...(needsReview ? { needs_review: true } : {}) }}
          onPress={() => setCategory(null)}
        />
        {CATEGORY_ORDER.map((value) => (
          <CategoryChip
            key={value}
            label={CATEGORY_LABELS[value]}
            selected={category === value}
            filters={{
              status,
              category: value,
              ...(needsReview ? { needs_review: true } : {}),
            }}
            onPress={() => setCategory(category === value ? null : value)}
          />
        ))}
      </ScrollView>
      <View style={styles.statusRow}>
        <Segmented
          accessibilityLabel="Estado"
          options={segmentOptions}
          // Nothing is highlighted in the default view (see `StatusChoice`).
          value={statusChoice as SegmentValue}
          onChange={(value) => setStatusChoice(statusChoice === value ? null : value)}
        />
        {needsReview ? (
          <FilterChip
            label="Solo pendientes de revisión"
            selected
            onPress={() => setNeedsReview(false)}
            testID="review-filter"
          />
        ) : null}
      </View>
      {pendingReview > 0 ? (
        <Banner
          testID="review-banner"
          icon={{ ios: 'exclamationmark.triangle', android: 'warning', web: 'warning' }}
          text={`${plural(pendingReview, 'prenda pendiente', 'prendas pendientes')} de revisión. Confirma lo que hemos detectado.`}
          actionLabel="Revisar"
          onAction={openReview}
        />
      ) : null}
      {softError ? (
        <Banner
          testID="wardrobe-soft-error"
          icon={{ ios: 'exclamationmark.triangle', android: 'warning', web: 'warning' }}
          text={softError.message || 'No se pudo actualizar el armario.'}
          actionLabel="Reintentar"
          onAction={retrySoftError}
        />
      ) : null}
    </View>
  );

  let empty = null;
  if (query.isPending) {
    empty = <LoadingState variant="grid" />;
  } else if (query.isError && !query.data) {
    empty = <ErrorState message={query.error.message} onRetry={() => void query.refetch()} />;
  } else if (items.length === 0) {
    empty = filtered ? (
      <View style={styles.emptyBox}>
        <EmptyState title="Nada por aquí" description="Prueba con otra categoría o estado." />
        <Button label="Quitar filtros" variant="secondary" onPress={clearFilters} />
      </View>
    ) : (
      <View style={styles.emptyBox}>
        <EmptyState
          title="Tu armario está vacío"
          description="Añade tu primera prenda para empezar a construir tu armario."
        />
        <Button label="Añadir prenda" onPress={() => router.push('/(tabs)/add')} />
      </View>
    );
  }

  // The "+ Añadir prenda" tile closes the grid once everything is loaded (not under Archivadas).
  const showAddTile = items.length > 0 && !query.hasNextPage && statusChoice !== 'archived';
  type Tile = (typeof items)[number] | { id: typeof ADD_TILE_ID; add: true };
  const data: Tile[] = [...items];
  if (showAddTile) data.push({ id: ADD_TILE_ID, add: true });

  return (
    <Screen scroll={false} style={styles.screen}>
      <FlatList
        testID="wardrobe-list"
        key={columns}
        data={data}
        keyExtractor={(item) => item.id}
        numColumns={columns}
        columnWrapperStyle={columns > 1 ? styles.gridRow : undefined}
        contentContainerStyle={styles.list}
        showsVerticalScrollIndicator={false}
        ListHeaderComponent={header}
        ListEmptyComponent={empty}
        renderItem={({ item }) => (
          <View style={{ width: cardWidth }}>
            {'add' in item ? (
              <AddGarmentTile onPress={() => router.push('/(tabs)/add')} />
            ) : (
              <GarmentCard item={item} onPress={(id) => router.push(`/garments/${id}`)} />
            )}
          </View>
        )}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void refresh()} />}
        ListFooterComponent={
          query.hasNextPage ? (
            <View style={styles.more}>
              <Button
                label={query.isFetchingNextPage ? 'Cargando…' : 'Cargar más'}
                accessibilityLabel="Cargar más"
                variant="secondary"
                disabled={query.isFetchingNextPage}
                onPress={() => void query.fetchNextPage()}
              />
            </View>
          ) : null
        }
      />
    </Screen>
  );
}

function CategoryChip({
  label,
  selected,
  filters,
  onPress,
}: {
  label: string;
  selected: boolean;
  filters: CountFilters;
  onPress: () => void;
}) {
  const count = useTotal(filters);
  return <FilterChip label={label} count={count} selected={selected} onPress={onPress} />;
}

const styles = StyleSheet.create({
  screen: { flex: 1, paddingTop: 0 },
  list: { gap: GAP + 6, paddingBottom: spacing.xxl },
  header: { gap: spacing.lg, paddingBottom: spacing.sm },
  titleBlock: { gap: 6, paddingTop: spacing.md },
  // A horizontal ScrollView must not grow: on web it would otherwise stretch to fill the column.
  row: { flexGrow: 0, flexShrink: 0 },
  // Status control: the segments shrink to the screen width, so no horizontal scroll here.
  statusRow: { gap: spacing.sm, alignItems: 'flex-start' },
  chips: { gap: spacing.sm, alignItems: 'center', paddingVertical: 2 },
  gridRow: { gap: GAP },
  emptyBox: { alignItems: 'center', gap: spacing.lg, paddingVertical: spacing.xxl },
  more: { alignItems: 'center', paddingTop: spacing.sm },
});
