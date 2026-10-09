import type { paths } from './schema';

export type GarmentFilters = NonNullable<paths['/garments']['get']['parameters']['query']>;

/**
 * Central TanStack Query keys. Lists live under `['garments', 'list', ...]` and
 * details under `['garments', 'detail', id]` so a mutation can invalidate both
 * without touching unrelated queries (UI-REQ-016).
 */
export const queryKeys = {
  garments: {
    all: ['garments'] as const,
    lists: () => ['garments', 'list'] as const,
    list: (filters: GarmentFilters = {}) => ['garments', 'list', filters] as const,
    infinite: (filters: GarmentFilters = {}) => ['garments', 'list', filters, 'infinite'] as const,
    detail: (id: string) => ['garments', 'detail', id] as const,
  },
  jobs: {
    all: ['jobs'] as const,
    detail: (id: string) => ['jobs', id] as const,
  },
  /**
   * Hoy's looks. `version` counts wardrobe changes (see `bumpWardrobeVersion`); one batch of
   * proposals lives under `generate(date, version, round)`, and what Hoy already showed from it
   * under `today(date, version)`. Persisted on native (`offline/persistence.ts`).
   */
  outfits: {
    all: ['outfits'] as const,
    version: ['outfits', 'version'] as const,
    generates: () => ['outfits', 'generate'] as const,
    generate: (date: string, version: number, round: number) =>
      ['outfits', 'generate', date, version, round] as const,
    today: (date: string, version: number) => ['outfits', 'today', date, version] as const,
  },
  /**
   * Virtual try-on. `byLook` maps a look (its sorted garment ids, see `lookKey`) to the id of its
   * latest render; `detail` holds the polled render. Persisted on native (`offline/persistence.ts`).
   */
  tryon: {
    all: ['tryon'] as const,
    capabilities: ['tryon', 'capabilities'] as const,
    details: () => ['tryon', 'detail'] as const,
    detail: (id: string) => ['tryon', 'detail', id] as const,
    byLooks: () => ['tryon', 'byLook'] as const,
    byLook: (lookKey: string) => ['tryon', 'byLook', lookKey] as const,
  },
  /** Historial; invalidated when the wear log changes. */
  history: { all: ['history'] as const },
  settings: ['settings'] as const,
  /** Bookkeeping of the offline sync (native only); persisted with the cache. */
  sync: { last: ['sync', 'last'] as const },
};
