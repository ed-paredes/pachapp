import type { QueryClient } from '@tanstack/react-query';

import { ApiError } from '@/api-client/errors';
import { queryKeys, type GarmentFilters } from '@/api-client/query-keys';
import { fetchGarmentDetail, fetchGarmentList, nextGarmentPage } from '@/hooks/useGarments';
import { fetchSettings } from '@/hooks/useSettings';
import { CATEGORY_ORDER } from '@/lib/labels';
import { USAGE_PAGE_SIZE } from '@/lib/wardrobe-usage';

import { runPool } from './pool';

/** Simultaneous requests while syncing: enough to be quick, few enough for a home PC. */
export const SYNC_CONCURRENCY = 4;

const ARMARIO_PAGE_SIZE = 50;
const DEFAULT_STATUS: GarmentFilters['status'] = ['active', 'laundry'];
const ALL_STATUS: GarmentFilters['status'] = ['active', 'laundry', 'archived'];

type ListFilters = Omit<GarmentFilters, 'page'>;

/** Every garment lives in this list; its pages give the ids whose details are synced. */
const ALL_FILTERS: ListFilters = {
  status: ALL_STATUS,
  sort: 'created_at',
  order: 'desc',
  page_size: ARMARIO_PAGE_SIZE,
};

/**
 * The Armario grid as each status view shows it. These filters must stay identical to the ones
 * the screens build (`app/(tabs)/wardrobe.tsx`), or the screens will not find the synced data.
 */
const INFINITE_FILTERS: ListFilters[] = [
  { ...ALL_FILTERS, status: DEFAULT_STATUS },
  { ...ALL_FILTERS, status: ['active'] },
  { ...ALL_FILTERS, status: ['laundry'] },
  { ...ALL_FILTERS, status: ['archived'] },
];

/**
 * Plain lists the screens read: the Armario counters and review banner (page size 1), Hoy and
 * Historial. Same rule as above: keep them identical to the screens' filters.
 */
const LIST_FILTERS: GarmentFilters[] = [
  { status: DEFAULT_STATUS, page_size: 1 },
  { status: ['active'], page_size: 1 },
  { status: ['laundry'], page_size: 1 },
  { status: ['archived'], page_size: 1 },
  { status: ALL_STATUS, page_size: 1 },
  { status: DEFAULT_STATUS, needs_review: true, page_size: 1 },
  ...CATEGORY_ORDER.map((category) => ({ status: DEFAULT_STATUS, category, page_size: 1 })),
  { status: ['laundry'], page_size: 2 },
  { status: ['active'], sort: 'wear_count', order: 'desc', page_size: USAGE_PAGE_SIZE },
  { status: ['active'], sort: 'wear_count', order: 'asc', page_size: 4 },
  { status: ['active'], sort: 'last_worn_at', order: 'asc', page_size: 4 },
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

let running: Promise<SyncResult> | null = null;

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
 * query cache under the keys the screens use, so it can be browsed offline. One run at a time;
 * a second call joins the running one. A failed run keeps the previous sync stamp.
 */
export function syncWardrobe(queryClient: QueryClient): Promise<SyncResult> {
  running ??= runSync(queryClient).finally(() => {
    running = null;
  });
  return running;
}
