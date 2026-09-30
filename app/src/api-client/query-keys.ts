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
  settings: ['settings'] as const,
};
