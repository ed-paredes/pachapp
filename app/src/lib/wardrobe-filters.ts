import type { GarmentFilters } from '@/api-client/query-keys';
import type { components } from '@/api-client/schema';

import { USAGE_PAGE_SIZE } from './wardrobe-usage';

/**
 * The garment-list filters the screens read, in one place. The offline sync stores its data under
 * the query keys these produce, so a screen and the sync can never drift apart: both import them.
 */

type GarmentStatus = components['schemas']['GarmentStatus'];

export type ListFilters = Omit<GarmentFilters, 'page'>;
export type CountFilters = Pick<GarmentFilters, 'status' | 'category' | 'needs_review'>;

/** Armario grid page size. */
export const ARMARIO_PAGE_SIZE = 50;

/** The default Armario view: active and laundry together (UI-REQ-004). */
export const DEFAULT_STATUS: GarmentStatus[] = ['active', 'laundry'];
export const ALL_STATUS: GarmentStatus[] = ['active', 'laundry', 'archived'];

/** Hoy names this many garments in the laundry notice. */
export const LAUNDRY_NAMES = 2;
/** Historial lists this many pieces per section. */
export const HISTORY_LIST_SIZE = 4;

/** The Armario grid (infinite list) for a status view and optional category / review scope. */
export function armarioFilters(scope: CountFilters & { status: GarmentStatus[] }): ListFilters {
  return {
    status: scope.status,
    sort: 'created_at',
    order: 'desc',
    page_size: ARMARIO_PAGE_SIZE,
    ...(scope.category ? { category: scope.category } : {}),
    ...(scope.needs_review ? { needs_review: true } : {}),
  };
}

/** A counter: one cheap request (page size 1) whose `total` is the number shown. */
export function countFilters(filters: CountFilters): GarmentFilters {
  return { ...filters, page_size: 1 };
}

/** Hoy: garments in the laundry, for the notice. */
export const LAUNDRY_FILTERS: GarmentFilters = { status: ['laundry'], page_size: LAUNDRY_NAMES };

/** Hoy and Historial: the active wardrobe, most worn first (shared request). */
export const USAGE_FILTERS: GarmentFilters = {
  status: ['active'],
  sort: 'wear_count',
  order: 'desc',
  page_size: USAGE_PAGE_SIZE,
};

/** Historial: never-worn first (the API sorts nulls last on `last_worn_at`). */
export const UNWORN_FILTERS: GarmentFilters = {
  status: ['active'],
  sort: 'wear_count',
  order: 'asc',
  page_size: HISTORY_LIST_SIZE,
};

/** Historial: the ones waiting longest to be worn. */
export const STALE_FILTERS: GarmentFilters = {
  status: ['active'],
  sort: 'last_worn_at',
  order: 'asc',
  page_size: HISTORY_LIST_SIZE,
};
