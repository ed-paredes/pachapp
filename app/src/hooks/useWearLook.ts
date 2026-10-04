import { useMutation, useQueryClient } from '@tanstack/react-query';

import { ApiError, unwrap } from '@/api-client/errors';
import { apiClient } from '@/api-client/http-client';
import { queryKeys } from '@/api-client/query-keys';
import { localDateKey } from '@/lib/look-day';

import type { ApiProposal } from './useGenerateOutfits';

/** The day was already logged: Hoy asks before replacing it. Keeps the saved outfit for the retry. */
export class WearConflictError extends Error {
  readonly outfitId: string;
  readonly date: string;

  constructor(outfitId: string, date: string) {
    super('The day already has an outfit');
    this.name = 'WearConflictError';
    this.outfitId = outfitId;
    this.date = date;
  }
}

export type WearVariables = {
  proposal: ApiProposal;
  /** Outfit saved by the attempt that hit the conflict: reused when replacing. */
  outfitId?: string;
  /** Replace the day's outfit (`PUT /wear-log/{date}`) instead of logging it. */
  replaceDate?: string;
};

async function saveOutfit(proposal: ApiProposal): Promise<string> {
  const outfit = unwrap(
    await apiClient.POST('/outfits', {
      body: {
        source: 'generated',
        items: proposal.items.map((item) => ({
          garment_id: item.garment_id,
          slot: item.slot,
          layer: item.layer,
        })),
        score: proposal.score,
        score_breakdown: proposal.score_breakdown,
        explanation: proposal.explanation,
        rating: 0,
        is_favorite: false,
      },
    }),
  );
  return outfit.id;
}

/**
 * "Me lo pongo": saves the proposal as an outfit (`POST /outfits`) and logs it for today
 * (`POST /wear-log`). When today already has one the API answers `409 WEAR_LOG_CONFLICT`; this
 * throws a `WearConflictError` so the screen can ask, and a second call with `replaceDate` swaps
 * it (`PUT /wear-log/{date}`). The wear counts changed either way: garments and Historial refresh.
 */
export function useWearLook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ proposal, outfitId, replaceDate }: WearVariables) => {
      const id = outfitId ?? (await saveOutfit(proposal));
      if (replaceDate) {
        return unwrap(
          await apiClient.PUT('/wear-log/{date}', {
            params: { path: { date: replaceDate } },
            body: { outfit_id: id },
          }),
        );
      }
      try {
        return unwrap(await apiClient.POST('/wear-log', { body: { outfit_id: id } }));
      } catch (error) {
        // Only a conflict that names the day's existing entry opens the replace question; any
        // other failure (e.g. `WEAR_LOG_WRITE_FAILED`) is a plain error the user can retry.
        if (
          error instanceof ApiError &&
          error.code === 'WEAR_LOG_CONFLICT' &&
          typeof error.details?.outfit_id === 'string'
        ) {
          const date = error.details.date;
          throw new WearConflictError(
            id,
            typeof date === 'string' ? date : localDateKey(new Date()),
          );
        }
        throw error;
      }
    },
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.garments.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.history.all }),
      ]),
  });
}
