import { hashKey, type QueryClient } from '@tanstack/react-query';

import { ApiError } from '@/api-client/errors';
import { queryKeys, type GarmentFilters } from '@/api-client/query-keys';
import { fetchGarmentDetail, fetchGarmentList, nextGarmentPage } from '@/hooks/useGarments';
import { fetchSettings } from '@/hooks/useSettings';
import { CATEGORY_ORDER } from '@/lib/labels';
import {
  ALL_STATUS,
  armarioFilters,
  countFilters,
  DEFAULT_STATUS,
  LAUNDRY_FILTERS,
  type ListFilters,
  STALE_FILTERS,
  UNWORN_FILTERS,
  USAGE_FILTERS,
} from '@/lib/wardrobe-filters';

import { garmentImageUrls, prefetchGarmentImages } from './images';
import { runPool } from './pool';

/** Simultaneous requests while syncing: enough to be quick, few enough for a home PC. */
export const SYNC_CONCURRENCY = 4;

/**
 * Every filter below comes from `@/lib/wardrobe-filters`, the same builders and constants the
 * screens use, so the synced data always lands under the keys the screens read.
 *
 * Every garment lives in the all-status list; its pages give the ids whose details are synced.
 */
const ALL_FILTERS: ListFilters = armarioFilters({ status: ALL_STATUS });

/** The Armario grid as each status view shows it. */
const STATUS_VIEWS: NonNullable<GarmentFilters['status']>[] = [
  DEFAULT_STATUS,
  ['active'],
  ['laundry'],
  ['archived'],
];
const INFINITE_FILTERS: ListFilters[] = STATUS_VIEWS.map((status) => armarioFilters({ status }));

/**
 * Plain lists the screens read: the Armario counters and review banner (page size 1), Hoy and
 * Historial.
 */
const LIST_FILTERS: GarmentFilters[] = [
  countFilters({ status: DEFAULT_STATUS }),
  countFilters({ status: ['active'] }),
  countFilters({ status: ['laundry'] }),
  countFilters({ status: ['archived'] }),
  countFilters({ status: ALL_STATUS }),
  countFilters({ status: DEFAULT_STATUS, needs_review: true }),
  ...CATEGORY_ORDER.map((category) => countFilters({ status: DEFAULT_STATUS, category })),
  LAUNDRY_FILTERS,
  USAGE_FILTERS,
  UNWORN_FILTERS,
  STALE_FILTERS,
];

type Page = Awaited<ReturnType<typeof fetchGarmentList>>;

/** Fetches every page of an Armario list and stores it as the infinite query the grid reads. */
async function syncInfiniteList(queryClient: QueryClient, filters: ListFilters): Promise<Page[]> {
  const pages: Page[] = [];
  for (let param: number | undefined = 1; param !== undefined;) {
    const page: Page = await fetchGarmentList({ ...filters, page: param });
    pages.push(page);
    param = nextGarmentPage(page, pages);
  }
  queryClient.setQueryData(queryKeys.garments.infinite(filters), {
    pages,
    pageParams: pages.map((_, index) => index + 1),
  });
  return pages;
}

async function syncDetail(queryClient: QueryClient, id: string): Promise<void> {
  try {
    queryClient.setQueryData(queryKeys.garments.detail(id), await fetchGarmentDetail(id));
  } catch (error) {
    // Deleted since the list was read: nothing to keep. Anything else aborts the sync.
    if (!(error instanceof ApiError && error.status === 404)) throw error;
  }
}

export type SyncResult = { ok: true; syncedAt: number } | { ok: false; error: unknown };

/** One run at a time per client; a second call joins it. */
const running = new WeakMap<QueryClient, Promise<SyncResult>>();

/**
 * Drops what the saved cache has no reason to keep after a successful sync: details of garments
 * that are not in the wardrobe any more, and garment lists under filters nobody syncs (one-off
 * filter combinations the user browsed once). Queries a screen is watching right now stay.
 *
 * Size: the persisted cache is a single AsyncStorage row. Around 300 garments it measures about
 * 0.5-1.2 MB (five Armario lists repeat every garment, plus one detail each). The Android row
 * limit is about 2 MB, so growth must stay bounded: without pruning, every filter ever browsed
 * and every deleted garment would stay forever. Past roughly 600 garments the single row no
 * longer fits and a chunked persister would be needed (see `createPersister`).
 */
export function pruneSyncedCache(queryClient: QueryClient, garmentIds: ReadonlySet<string>): void {
  const keptLists = new Set<string>(
    [...INFINITE_FILTERS, ALL_FILTERS].map((filters) =>
      hashKey(queryKeys.garments.infinite(filters)),
    ),
  );
  LIST_FILTERS.forEach((filters) => keptLists.add(hashKey(queryKeys.garments.list(filters))));

  const cache = queryClient.getQueryCache();
  for (const query of cache.findAll({ queryKey: queryKeys.garments.all })) {
    if (query.getObserversCount() > 0) continue;
    const [, kind, detail] = query.queryKey;
    const stale =
      kind === 'detail'
        ? !garmentIds.has(String(detail))
        : kind === 'list'
          ? !keptLists.has(query.queryHash)
          : false;
    if (stale) cache.remove(query);
  }
}

async function runSync(queryClient: QueryClient): Promise<SyncResult> {
  try {
    // The all-status list first: it names every garment.
    const everything = await syncInfiniteList(queryClient, ALL_FILTERS);
    const ids = [...new Set(everything.flatMap((page) => page.items.map((item) => item.id)))];

    await runPool(INFINITE_FILTERS, SYNC_CONCURRENCY, async (filters) => {
      await syncInfiniteList(queryClient, filters);
    });
    await runPool(LIST_FILTERS, SYNC_CONCURRENCY, async (filters) => {
      queryClient.setQueryData(queryKeys.garments.list(filters), await fetchGarmentList(filters));
    });
    queryClient.setQueryData(queryKeys.settings, await fetchSettings());
    await runPool(ids, SYNC_CONCURRENCY, (id) => syncDetail(queryClient, id));

    // Last: the images are the heaviest part and a few missing ones do not spoil the data.
    await prefetchGarmentImages(garmentImageUrls(everything.flatMap((page) => page.items)));

    pruneSyncedCache(queryClient, new Set(ids));

    const syncedAt = Date.now();
    queryClient.setQueryData(queryKeys.sync.last, syncedAt);
    return { ok: true, syncedAt };
  } catch (error) {
    // Not marked as synced: the previous stamp keeps saying when the saved data is from.
    return { ok: false, error };
  }
}

/**
 * Copies the whole wardrobe (every list page and every garment detail, plus settings) into the
 * query cache under the keys the screens use, and their thumbnails and cutouts onto disk, so
 * it can be browsed offline. One run at a time per
 * client; a second call joins the running one. A failed run keeps the previous sync stamp.
 */
export function syncWardrobe(queryClient: QueryClient): Promise<SyncResult> {
  const current = running.get(queryClient);
  if (current) return current;
  const started = runSync(queryClient).finally(() => running.delete(queryClient));
  running.set(queryClient, started);
  return started;
}
