import { skipToken, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';

import { unwrap } from '@/api-client/errors';
import { apiClient } from '@/api-client/http-client';
import { queryKeys } from '@/api-client/query-keys';
import type { components } from '@/api-client/schema';
import { msUntilEndOfDay } from '@/lib/look-day';

export type GenerateResponse = components['schemas']['GenerateOutfitsResponse'];
export type ApiProposal = components['schemas']['OutfitProposal'];

/** The API accepts at most this many excluded sets per request. */
export const MAX_EXCLUDE_SETS = 50;

/** The garment ids of a proposal, sorted: the identity of a look (order does not matter). */
export function proposalSet(proposal: ApiProposal): string[] {
  return proposal.items.map((item) => item.garment_id).sort();
}

/** One `POST /outfits/generate`; `exclude` are the sets already shown today. */
export async function fetchGenerate(exclude: string[][]): Promise<GenerateResponse> {
  return unwrap(
    await apiClient.POST('/outfits/generate', {
      body: exclude.length ? { exclude_sets: exclude.slice(-MAX_EXCLUDE_SETS) } : {},
    }),
  );
}

/** Every set of the earlier rounds of this day and wardrobe version (the "already shown" ones). */
export function excludedSets(
  queryClient: QueryClient,
  date: string,
  version: number,
  round: number,
): string[][] {
  const sets: string[][] = [];
  for (let earlier = 0; earlier < round; earlier += 1) {
    const batch = queryClient.getQueryData<GenerateResponse>(
      queryKeys.outfits.generate(date, version, earlier),
    );
    batch?.proposals.forEach((proposal) => sets.push(proposalSet(proposal)));
  }
  return sets;
}

/**
 * Options of one batch of proposals. Generation is a POST, but it reads: it is a query (cached,
 * persisted on native, never a mutation) that stays fresh until the end of the local day.
 */
export function generateOptions(
  queryClient: QueryClient,
  date: string,
  version: number,
  round: number,
  now: Date,
) {
  return {
    queryKey: queryKeys.outfits.generate(date, version, round),
    queryFn: () => fetchGenerate(excludedSets(queryClient, date, version, round)),
    staleTime: msUntilEndOfDay(now),
  };
}

/** How many times the wardrobe changed (persisted with the cache): part of every batch's key. */
export function useWardrobeVersion(): number {
  // `skipToken`: read the (restored) cache entry, never fetch it.
  return useQuery<number>({ queryKey: queryKeys.outfits.version, queryFn: skipToken }).data ?? 0;
}

/**
 * The wardrobe changed (upload, edit, archive, laundry, delete): Hoy's batch is out of date, so
 * its key changes and the next visit proposes again. The old batches stay as the offline
 * fallback until a newer one arrives (`pruneOutfits`).
 */
export function bumpWardrobeVersion(queryClient: QueryClient): void {
  queryClient.setQueryData<number>(queryKeys.outfits.version, (current) => (current ?? 0) + 1);
}

/** Drops batches and bookkeeping of other days or wardrobe versions. */
export function pruneOutfits(queryClient: QueryClient, date: string, version: number): void {
  const cache = queryClient.getQueryCache();
  for (const query of cache.findAll({ queryKey: queryKeys.outfits.all })) {
    const [, kind, queryDate, queryVersion] = query.queryKey;
    if (kind !== 'generate' && kind !== 'today') continue;
    if (queryDate !== date || queryVersion !== version) cache.remove(query);
  }
}

/** The newest batch in the cache, of any day: what Hoy shows when it cannot generate. */
export function latestSavedBatch(queryClient: QueryClient): GenerateResponse | undefined {
  const saved = queryClient
    .getQueryCache()
    .findAll({ queryKey: queryKeys.outfits.generates() })
    .filter((query) => query.state.data !== undefined)
    .sort((a, b) => b.state.dataUpdatedAt - a.state.dataUpdatedAt);
  return saved[0]?.state.data as GenerateResponse | undefined;
}

/** `POST /outfits/generate` as a query, one batch per `(date, wardrobe version, round)`. */
export function useGenerateOutfits({
  date,
  version,
  round,
  now,
  enabled,
}: {
  date: string;
  version: number;
  round: number;
  now: Date;
  enabled: boolean;
}) {
  const queryClient = useQueryClient();
  return useQuery({ ...generateOptions(queryClient, date, version, round, now), enabled });
}
