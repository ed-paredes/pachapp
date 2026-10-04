import { QueryClient } from '@tanstack/react-query';

import { Image } from 'expo-image';

import { queryKeys } from '../src/api-client/query-keys';
import { runPool } from '../src/offline/pool';
import { syncWardrobe } from '../src/offline/sync';

const TOTAL = 120;
const ids = Array.from({ length: TOTAL }, (_, index) => `g${index}`);

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const listItem = (id: string) => ({
  id,
  category: 'top',
  status: 'active',
  img_thumb: `thumb/${id}.webp`,
  img_cutout: `cutout/${id}.png`,
  job: null,
});

/** Serves the whole API; `delayMs` keeps requests in flight so concurrency can be measured. */
function installApi({
  delayMs = 0,
  failDetail,
}: { delayMs?: number; failDetail?: (id: string) => Response | Error | undefined } = {}) {
  const stats = { inFlight: 0, maxInFlight: 0, detailCalls: 0, listCalls: 0, urls: [] as string[] };
  globalThis.fetch = jest.fn(async (input: Request | string) => {
    const url = new URL(typeof input === 'string' ? input : input.url);
    stats.urls.push(url.pathname + url.search);
    stats.inFlight += 1;
    stats.maxInFlight = Math.max(stats.maxInFlight, stats.inFlight);
    try {
      if (delayMs) await new Promise((resolve) => setTimeout(resolve, delayMs));
      if (url.pathname === '/garments') {
        stats.listCalls += 1;
        const page = Number(url.searchParams.get('page') ?? '1');
        const size = Number(url.searchParams.get('page_size') ?? '50');
        const items = ids.slice((page - 1) * size, page * size).map(listItem);
        return json({ items, total: TOTAL, page, page_size: size });
      }
      if (url.pathname === '/settings') return json({ weights: {} });
      const detail = /^\/garments\/(.+)$/.exec(url.pathname);
      if (detail) {
        stats.detailCalls += 1;
        const failure = failDetail?.(detail[1]);
        if (failure instanceof Error) throw failure;
        if (failure) return failure;
        return json({ ...listItem(detail[1]), brand: 'Acme' });
      }
      return json({ error: { code: 'NOT_FOUND', message: 'nope' } }, 404);
    } finally {
      stats.inFlight -= 1;
    }
  }) as unknown as typeof fetch;
  return stats;
}

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
}

const realFetch = globalThis.fetch;
let prefetch: jest.SpyInstance;
beforeEach(() => {
  jest.spyOn(Image, 'getCachePathAsync').mockResolvedValue(null);
  prefetch = jest.spyOn(Image, 'prefetch').mockResolvedValue(true);
});
afterEach(() => {
  globalThis.fetch = realFetch;
  jest.restoreAllMocks();
});

describe('runPool', () => {
  it('never runs more than the limit at once and visits every item', async () => {
    let active = 0;
    let peak = 0;
    const seen: number[] = [];
    await runPool([1, 2, 3, 4, 5, 6, 7], 3, async (item) => {
      active += 1;
      peak = Math.max(peak, active);
      await new Promise((resolve) => setTimeout(resolve, 5));
      seen.push(item);
      active -= 1;
    });
    expect(peak).toBe(3);
    expect(seen.sort()).toEqual([1, 2, 3, 4, 5, 6, 7]);
  });

  it('stops starting work after a failure and rethrows it', async () => {
    const started: number[] = [];
    await expect(
      runPool([1, 2, 3, 4, 5, 6], 1, async (item) => {
        started.push(item);
        if (item === 2) throw new Error('boom');
      }),
    ).rejects.toThrow('boom');
    expect(started).toEqual([1, 2]);
  });
});

describe('syncWardrobe', () => {
  it('stores every list page and every detail under the keys the screens read', async () => {
    const stats = installApi();
    const client = makeClient();

    const result = await syncWardrobe(client);

    expect(result.ok).toBe(true);
    // Armario default view: all three 50-item pages, as the infinite query holds them.
    const armario = client.getQueryData<{ pages: { items: { id: string }[] }[] }>(
      queryKeys.garments.infinite({
        status: ['active', 'laundry'],
        sort: 'created_at',
        order: 'desc',
        page_size: 50,
      }),
    );
    expect(armario?.pages).toHaveLength(3);
    expect(armario?.pages.flatMap((page) => page.items)).toHaveLength(TOTAL);
    // Every garment detail, even those never opened.
    for (const id of ids) {
      expect(client.getQueryData(queryKeys.garments.detail(id))).toMatchObject({ id });
    }
    expect(stats.detailCalls).toBe(TOTAL);
    // A counter and a Hoy list, read by their own screens.
    expect(
      client.getQueryData(queryKeys.garments.list({ status: ['laundry'], page_size: 2 })),
    ).toMatchObject({ total: TOTAL });
    expect(client.getQueryData(queryKeys.settings)).toEqual({ weights: {} });
  });

  it('downloads every thumbnail and cutout to disk', async () => {
    installApi();
    await syncWardrobe(makeClient());

    const urls = prefetch.mock.calls.flatMap(([batch]) => batch as string[]);
    expect(urls).toHaveLength(TOTAL * 2);
    expect(urls).toContain('http://localhost:8000/images/thumb/g0.webp');
    expect(urls).toContain('http://localhost:8000/images/cutout/g119.png');
  });

  it('still counts as synced when some images could not be fetched', async () => {
    installApi();
    prefetch.mockResolvedValue(false);
    expect((await syncWardrobe(makeClient())).ok).toBe(true);
  });

  it('keeps at most four requests in flight', async () => {
    const stats = installApi({ delayMs: 2 });
    await syncWardrobe(makeClient());
    expect(stats.maxInFlight).toBeGreaterThan(1);
    expect(stats.maxInFlight).toBeLessThanOrEqual(4);
  });

  it('records the last successful sync time', async () => {
    installApi();
    const client = makeClient();
    const before = Date.now();
    const result = await syncWardrobe(client);
    const stored = client.getQueryData<number>(queryKeys.sync.last);
    expect(result).toEqual({ ok: true, syncedAt: stored });
    expect(stored).toBeGreaterThanOrEqual(before);
  });

  it('joins a sync that is already running instead of starting another', async () => {
    const stats = installApi({ delayMs: 1 });
    const client = makeClient();
    const [first, second] = await Promise.all([syncWardrobe(client), syncWardrobe(client)]);
    expect(first).toBe(second);
    expect(stats.detailCalls).toBe(TOTAL);
  });

  it('skips a garment deleted since the list was read', async () => {
    installApi({
      failDetail: (id) =>
        id === 'g3' ? json({ error: { code: 'NOT_FOUND', message: 'gone' } }, 404) : undefined,
    });
    const client = makeClient();
    const result = await syncWardrobe(client);
    expect(result.ok).toBe(true);
    expect(client.getQueryData(queryKeys.garments.detail('g3'))).toBeUndefined();
    expect(client.getQueryData(queryKeys.garments.detail('g4'))).toBeDefined();
  });

  it('does not stamp a sync that lost the connection, and keeps the previous stamp', async () => {
    installApi({
      failDetail: (id) => (id === 'g10' ? new TypeError('Network request failed') : undefined),
    });
    const client = makeClient();
    client.setQueryData(queryKeys.sync.last, 123);

    const result = await syncWardrobe(client);

    expect(result.ok).toBe(false);
    expect(client.getQueryData(queryKeys.sync.last)).toBe(123);
  });
});
