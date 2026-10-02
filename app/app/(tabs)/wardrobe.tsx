import { useRouter } from 'expo-router';
import { useState } from 'react';
import {
  FlatList,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from 'react-native';

import type { GarmentFilters } from '@/api-client/query-keys';
import type { components } from '@/api-client/schema';
import { Chip } from '@/components/Chip';
import { ContentContainer } from '@/components/ContentContainer';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { GarmentCard } from '@/components/GarmentCard';
import { LoadingState } from '@/components/LoadingState';
import { flattenGarmentPages, useInfiniteGarments } from '@/hooks/useGarments';
import { CATEGORY_LABELS, CATEGORY_ORDER } from '@/lib/labels';
import {
  CONTENT_MAX_WIDTH,
  colors,
  fontFamilies,
  fontSizes,
  gridColumns,
  radii,
  spacing,
} from '@/theme';

type Category = components['schemas']['GarmentCategory'];
type GarmentStatus = components['schemas']['GarmentStatus'];

const PAGE_SIZE = 50;
const PADDING = spacing.lg;
const GAP = spacing.md;

/** `null` = default (active + laundry, UI-REQ-004 default of the Armario). */
type StatusChoice = GarmentStatus | 'all' | null;

const STATUS_CHIPS: { value: Exclude<StatusChoice, null>; label: string }[] = [
  { value: 'active', label: 'Activas' },
  { value: 'laundry', label: 'Lavando' },
  { value: 'archived', label: 'Archivadas' },
  { value: 'all', label: 'Todas' },
];

function statusFilter(choice: StatusChoice): GarmentStatus[] {
  if (choice === null) return ['active', 'laundry'];
  if (choice === 'all') return ['active', 'laundry', 'archived'];
  return [choice];
}

/**
 * Armario (Wardrobe): grid of garments with filters, a "Revisar" badge on
 * garments pending review, processing placeholders, pull-to-refresh and
 * explicit loading / empty / error states (UI-REQ-004, UI-REQ-008).
 */
export default function WardrobeScreen() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  // Columns come from the content width (capped like the container) and a minimum card width.
  const columns = gridColumns(Math.min(width, CONTENT_MAX_WIDTH) - PADDING * 2, undefined, GAP);

  const [category, setCategory] = useState<Category | null>(null);
  const [statusChoice, setStatusChoice] = useState<StatusChoice>(null);
  const [needsReview, setNeedsReview] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const filters: Omit<GarmentFilters, 'page'> = {
    status: statusFilter(statusChoice),
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
  const softError = query.isError && query.data ? query.error : null;

  const clearFilters = () => {
    setCategory(null);
    setStatusChoice(null);
    setNeedsReview(false);
  };
  const retrySoftError = () => {
    if (query.isFetchNextPageError) void query.fetchNextPage();
    else void query.refetch();
  };
  const refresh = async () => {
    setRefreshing(true);
    try {
      await query.refetch();
    } finally {
      setRefreshing(false);
    }
  };

  let body;
  if (query.isPending) {
    body = <LoadingState variant="grid" />;
  } else if (query.isError && !query.data) {
    body = <ErrorState message={query.error.message} onRetry={() => void query.refetch()} />;
  } else if (items.length === 0) {
    body = filtered ? (
      <View style={styles.emptyBox}>
        <EmptyState
          title="Ninguna prenda coincide con estos filtros"
          description="Prueba con otros filtros o quítalos para ver todo tu armario."
        />
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Quitar filtros"
          onPress={clearFilters}
          style={styles.action}
        >
          <Text style={styles.actionText}>Quitar filtros</Text>
        </Pressable>
      </View>
    ) : (
      <View style={styles.emptyBox}>
        <EmptyState
          title="Tu armario está vacío"
          description="Añade tu primera prenda para empezar a construir tu armario."
        />
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Añadir prenda"
          onPress={() => router.push('/(tabs)/add')}
          style={styles.action}
        >
          <Text style={styles.actionText}>Añadir prenda</Text>
        </Pressable>
      </View>
    );
  } else {
    body = (
      <FlatList
        testID="wardrobe-list"
        key={columns}
        data={items}
        keyExtractor={(item) => item.id}
        numColumns={columns}
        columnWrapperStyle={styles.row}
        contentContainerStyle={styles.list}
        renderItem={({ item }) => (
          <View style={{ width: `${100 / columns}%`, paddingHorizontal: GAP / 2 }}>
            <GarmentCard item={item} onPress={(id) => router.push(`/garments/${id}`)} />
          </View>
        )}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void refresh()} />}
        ListFooterComponent={
          query.hasNextPage ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Cargar más"
              disabled={query.isFetchingNextPage}
              onPress={() => void query.fetchNextPage()}
              style={styles.action}
            >
              <Text style={styles.actionText}>
                {query.isFetchingNextPage ? 'Cargando…' : 'Cargar más'}
              </Text>
            </Pressable>
          ) : null
        }
      />
    );
  }

  return (
    <ContentContainer style={styles.container}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.chipRow}
        contentContainerStyle={styles.chips}
      >
        <Chip
          group="Categoría"
          label="Todas"
          selected={category === null}
          onPress={() => setCategory(null)}
        />
        {CATEGORY_ORDER.map((value) => (
          <Chip
            key={value}
            group="Categoría"
            label={CATEGORY_LABELS[value]}
            selected={category === value}
            onPress={() => setCategory(category === value ? null : value)}
          />
        ))}
      </ScrollView>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.chipRow}
        contentContainerStyle={styles.chips}
      >
        {STATUS_CHIPS.map((chip) => (
          <Chip
            key={chip.value}
            group="Estado"
            label={chip.label}
            selected={statusChoice === chip.value}
            onPress={() => setStatusChoice(statusChoice === chip.value ? null : chip.value)}
          />
        ))}
        <Chip
          group="Filtro"
          label="Pendientes de revisión"
          selected={needsReview}
          onPress={() => setNeedsReview(!needsReview)}
        />
      </ScrollView>
      {softError ? (
        <View style={styles.banner} accessibilityRole="alert" testID="wardrobe-soft-error">
          <Text style={styles.bannerText}>
            {softError.message || 'No se pudo actualizar el armario.'}
          </Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Reintentar"
            onPress={retrySoftError}
            style={styles.bannerAction}
          >
            <Text style={styles.actionText}>Reintentar</Text>
          </Pressable>
        </View>
      ) : null}
      <View style={styles.body}>{body}</View>
    </ContentContainer>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  // A horizontal ScrollView must not grow: on web it would otherwise stretch to fill the column.
  chipRow: { flexGrow: 0, flexShrink: 0 },
  chips: { gap: spacing.sm, alignItems: 'center', paddingHorizontal: PADDING, paddingVertical: 6 },
  body: { flex: 1 },
  list: { padding: PADDING - GAP / 2, gap: GAP },
  row: { alignItems: 'flex-start' },
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginHorizontal: PADDING,
    marginVertical: 6,
    padding: 10,
    borderRadius: radii.sm,
    backgroundColor: colors.errorSurface,
  },
  bannerText: {
    flex: 1,
    fontFamily: fontFamilies.body,
    fontSize: fontSizes.small,
    color: colors.error,
  },
  bannerAction: { padding: spacing.xs },
  emptyBox: { flex: 1 },
  action: { alignSelf: 'center', marginVertical: PADDING, padding: spacing.sm },
  actionText: {
    fontFamily: fontFamilies.bodySemiBold,
    fontSize: fontSizes.body,
    color: colors.olive,
  },
});
