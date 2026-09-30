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
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { GarmentCard } from '@/components/GarmentCard';
import { LoadingState } from '@/components/LoadingState';
import { flattenGarmentPages, useInfiniteGarments } from '@/hooks/useGarments';
import { CATEGORY_LABELS, CATEGORY_ORDER } from '@/lib/labels';

type Category = components['schemas']['GarmentCategory'];
type GarmentStatus = components['schemas']['GarmentStatus'];

const PAGE_SIZE = 50;
const PADDING = 16;
const GAP = 12;

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
  const columns = width >= 600 ? 3 : 2;

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
    <View style={styles.container}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
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
    </View>
  );
}

function Chip({
  group,
  label,
  selected,
  onPress,
}: {
  group: string;
  label: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${group}: ${label}`}
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[styles.chip, selected && styles.chipSelected]}
    >
      <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  chips: { gap: 8, paddingHorizontal: PADDING, paddingVertical: 6 },
  chip: {
    paddingVertical: 6,
    paddingHorizontal: 14,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#D0D5DD',
  },
  chipSelected: { backgroundColor: '#208AEF', borderColor: '#208AEF' },
  chipText: { fontSize: 13, fontWeight: '500' },
  chipTextSelected: { color: '#fff' },
  body: { flex: 1 },
  list: { padding: PADDING - GAP / 2, gap: GAP },
  row: { alignItems: 'flex-start' },
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginHorizontal: PADDING,
    marginVertical: 6,
    padding: 10,
    borderRadius: 8,
    backgroundColor: '#FEF3F2',
  },
  bannerText: { flex: 1, fontSize: 13, color: '#B42318' },
  bannerAction: { padding: 4 },
  emptyBox: { flex: 1 },
  action: { alignSelf: 'center', marginVertical: 16, padding: 8 },
  actionText: { fontSize: 16, fontWeight: '600', color: '#208AEF' },
});
