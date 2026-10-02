import { useRouter } from 'expo-router';
import { useMemo } from 'react';

import { HistoryView, type HistoryKpi, type RankItem } from '@/components/history';
import { useGarments } from '@/hooks/useGarments';
import { garmentName } from '@/lib/garment-name';
import { imageUrl } from '@/lib/image-url';
import { USAGE_PAGE_SIZE, wardrobeUsage } from '@/lib/wardrobe-usage';
import { colors } from '@/theme';

const LIST_SIZE = 4;
const DAY_MS = 24 * 60 * 60 * 1000;
/** A garment worn this long ago (or more) counts as forgotten. */
const FORGOTTEN_DAYS = 30;

type Listed = Parameters<typeof garmentName>[0] & {
  id: string;
  wear_count: number;
  last_worn_at: string | null;
  img_thumb: string | null;
  colors: { name: string; hex: string }[] | null;
};

/** "Hace 80 días" (the shared `formatLastWorn` switches to dates after two months). */
function daysAgo(iso: string, now: Date): string {
  const days = Math.floor((now.getTime() - new Date(iso).getTime()) / DAY_MS);
  return `Hace ${days} días`;
}

function toRow(item: Listed, detail: string, usage?: number): RankItem {
  return {
    id: item.id,
    name: garmentName(item),
    detail,
    color: item.colors?.[0]?.hex ?? colors.ink3,
    thumbUri: imageUrl(item.img_thumb),
    usage,
  };
}

/**
 * Historial. There is no wear-log endpoint yet, so the calendar, looks per month, cost per use
 * and trends are not shown (`calendar` stays undefined: the empty state shows). What the garment
 * list can say honestly is: the share of the wardrobe worn, how many pieces were never worn, the
 * most worn and the ones waiting longest. To connect the wear log, build the `calendar` props
 * (`month`, `days`, `onPrevious`, `onNext`) and the extra KPIs here and pass them down.
 */
export default function HistoryScreen() {
  const router = useRouter();
  const now = useMemo(() => new Date(), []);

  // Same request as Hoy, so the cache is shared: the active wardrobe, most worn first.
  const active = useGarments({
    status: ['active'],
    sort: 'wear_count',
    order: 'desc',
    page_size: USAGE_PAGE_SIZE,
  });
  // Never-worn first (the API sorts nulls last on `last_worn_at`, so they need `wear_count`).
  const unworn = useGarments({
    status: ['active'],
    sort: 'wear_count',
    order: 'asc',
    page_size: LIST_SIZE,
  });
  const stale = useGarments({
    status: ['active'],
    sort: 'last_worn_at',
    order: 'asc',
    page_size: LIST_SIZE,
  });

  const usage = active.data ? wardrobeUsage(active.data.items, active.data.total) : null;
  const kpis: HistoryKpi[] = [];
  // Nothing worn yet: a "0%" says nothing (Hoy hides it too), so only the unworn count shows.
  const anyWorn = (usage?.worn ?? 0) > 0;
  if (usage) {
    if (anyWorn) {
      kpis.push({ id: 'usage', value: `${usage.percent}%`, label: 'del armario usado' });
    }
    kpis.push({
      id: 'unworn',
      value: String(usage.total - usage.worn),
      label: usage.total - usage.worn === 1 ? 'prenda sin estrenar' : 'prendas sin estrenar',
    });
  }

  const worn = (active.data?.items ?? []).filter((item) => item.wear_count > 0).slice(0, LIST_SIZE);
  const top = worn[0]?.wear_count ?? 0;
  const mostWorn = worn.map((item) =>
    toRow(
      item,
      `${item.wear_count} ${item.wear_count === 1 ? 'uso' : 'usos'}`,
      top > 0 ? item.wear_count / top : 0,
    ),
  );

  const secondChance: RankItem[] = [
    ...(unworn.data?.items ?? [])
      .filter((item) => item.wear_count === 0)
      .map((item) => toRow(item, 'Sin estrenar')),
    ...(stale.data?.items ?? [])
      .filter(
        (item) =>
          item.last_worn_at !== null &&
          now.getTime() - new Date(item.last_worn_at).getTime() >= FORGOTTEN_DAYS * DAY_MS,
      )
      .map((item) => toRow(item, daysAgo(item.last_worn_at as string, now))),
  ].slice(0, LIST_SIZE);

  return (
    <HistoryView
      kpis={kpis}
      mostWorn={mostWorn}
      secondChance={secondChance}
      secondChanceTitle={anyWorn ? 'Dales otra oportunidad' : 'Aún sin estrenar'}
      onOpenGarment={(id) => router.push(`/garments/${id}`)}
    />
  );
}
