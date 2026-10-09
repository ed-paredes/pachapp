import { skipToken, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { queryKeys } from '@/api-client/query-keys';
import type { LookProposal } from '@/components/today/types';
import { localDateKey } from '@/lib/look-day';
import { toAltLook, toLookProposal, type GarmentIndex } from '@/lib/look-mapper';
import { useIsOffline } from '@/offline/reachability';

import { fetchGarmentDetail } from './useGarments';
import {
  excludedSets,
  generateOptions,
  latestSavedBatch,
  MAX_EXCLUDE_SETS,
  pruneOutfits,
  useGenerateOutfits,
  useWardrobeVersion,
  type ApiProposal,
} from './useGenerateOutfits';
import { pruneTryOn } from './useTryOn';
import { useWearLook, WearConflictError } from './useWearLook';

/** What Hoy already showed from the day's batches (persisted with the outfits cache on native). */
type TodayState = {
  /** Which batch (0 = the first request of the day) is on screen. */
  round: number;
  /** Index, in that batch, of the look of the day. */
  current: number;
  /** Indices of the batch already shown: "Otra sugerencia" moves to one that is not in it. */
  shown: number[];
  /** The last request for new looks came back empty: every combination was shown. */
  exhausted: boolean;
};

const INITIAL: TodayState = { round: 0, current: 0, shown: [0], exhausted: false };

export const MESSAGES = {
  worn: 'Look registrado para hoy',
  replaced: 'Outfit de hoy cambiado',
  wearFailed: 'No pudimos registrar el look. Inténtalo de nuevo.',
  moreFailed: 'No pudimos pedir más sugerencias. Inténtalo de nuevo.',
  noMoreOffline: 'No hay más sugerencias guardadas.',
  noMore: 'No quedan más combinaciones por hoy. Añade prendas para ver más.',
} as const;

export type TodayLooksStatus = 'idle' | 'loading' | 'ready' | 'empty' | 'error';

type Options = {
  now: Date;
  /** Wardrobe size as Hoy knows it; generation is skipped for an empty wardrobe. */
  wardrobeSize: number | 'loading' | 'unknown';
  /** Short confirmations and failures (the screen shows them as toasts). */
  notify: (message: string) => void;
};

/**
 * Hoy's looks. One batch of up to 5 proposals is generated per day (and again when the wardrobe
 * changes); the best is the look of the day and the rest its alternatives. "Otra sugerencia"
 * walks the batch without calling the backend, and only when all were shown asks for a new batch
 * that excludes everything shown (the seed only breaks ties, so a new seed would repeat them).
 */
export function useTodayLooks({ now, wardrobeSize, notify }: Options) {
  const queryClient = useQueryClient();
  const offline = useIsOffline();
  const date = localDateKey(now);
  const version = useWardrobeVersion();
  const todayKey = queryKeys.outfits.today(date, version);

  const stored = useQuery({ queryKey: todayKey, queryFn: skipToken }).data as
    TodayState | undefined;
  const state = stored ?? INITIAL;
  const save = (next: TodayState) => queryClient.setQueryData(todayKey, next);

  const batchQuery = useGenerateOutfits({
    date,
    version,
    round: state.round,
    now,
    enabled: wardrobeSize !== 0 && wardrobeSize !== 'loading',
  });
  // Without a batch for today (offline, or the request failed) Hoy keeps showing the last one saved.
  const fresh = batchQuery.data;
  const batch =
    fresh ?? (batchQuery.isError || offline ? latestSavedBatch(queryClient) : undefined);
  const proposals = useMemo<ApiProposal[]>(() => batch?.proposals ?? [], [batch]);

  useEffect(() => {
    if (fresh) {
      pruneOutfits(queryClient, date, version);
      pruneTryOn(queryClient);
    }
  }, [fresh, queryClient, date, version]);

  const ids = useMemo(
    () => [...new Set(proposals.flatMap((p) => p.items.map((item) => item.garment_id)))],
    [proposals],
  );
  const details = useQueries({
    queries: ids.map((id) => ({
      queryKey: queryKeys.garments.detail(id),
      queryFn: () => fetchGarmentDetail(id),
    })),
  });
  const index: GarmentIndex = new Map(
    details.flatMap((query) => (query.data ? [[query.data.id, query.data] as const] : [])),
  );
  const resolving = details.some((query) => query.isPending);

  // Proposals whose garments could not be loaded (deleted meanwhile) are left out.
  const available = proposals
    .map((proposal, position) => ({ proposal, position, look: toLookProposal(proposal, index) }))
    .filter((entry) => entry.look !== null);
  const current = available.find((entry) => entry.position === state.current) ?? available[0];
  const proposal: LookProposal | undefined = current?.look ?? undefined;
  const alternatives = available
    .filter((entry) => entry !== current)
    .flatMap((entry) => toAltLook(String(entry.position), entry.proposal, index) ?? []);

  const [requesting, setRequesting] = useState(false);
  const [pending, setPending] = useState<{
    outfitId: string;
    date: string;
    round: number;
    position: number;
  } | null>(null);
  // The question belongs to the look it was asked for: another look on screen drops it.
  const conflict =
    pending && pending.round === state.round && pending.position === current?.position
      ? pending
      : null;
  const wear = useWearLook();

  const unseen = available.find(
    (entry) => entry !== current && !state.shown.includes(entry.position),
  );
  // The API bounds the excluded sets: past it, nothing more can be asked for today.
  const exhausted =
    state.exhausted ||
    excludedSets(queryClient, date, version, state.round + 1).length > MAX_EXCLUDE_SETS;
  const canRequestMore = !!fresh && !offline && !exhausted;

  const show = (position: number) => {
    setPending(null);
    save({ ...state, current: position, shown: [...new Set([...state.shown, position])] });
  };

  const shuffle = async () => {
    if (unseen) return show(unseen.position);
    if (!canRequestMore || requesting) return undefined;
    setPending(null);
    setRequesting(true);
    try {
      const next = state.round + 1;
      const more = await queryClient.fetchQuery(
        generateOptions(queryClient, date, version, next, now),
      );
      if (more.proposals.length) save({ round: next, current: 0, shown: [0], exhausted: false });
      else save({ ...state, exhausted: true });
    } catch {
      notify(MESSAGES.moreFailed);
    } finally {
      setRequesting(false);
    }
    return undefined;
  };

  const shuffleNote = unseen
    ? undefined
    : offline
      ? MESSAGES.noMoreOffline
      : exhausted
        ? MESSAGES.noMore
        : undefined;

  const wearCurrent = (variables: { outfitId?: string; replaceDate?: string } = {}) => {
    if (!current) return;
    const { round } = state;
    const { position } = current;
    wear.mutate(
      { proposal: current.proposal, ...variables },
      {
        onSuccess: () => {
          setPending(null);
          notify(variables.replaceDate ? MESSAGES.replaced : MESSAGES.worn);
        },
        onError: (error) => {
          if (error instanceof WearConflictError) {
            setPending({ outfitId: error.outfitId, date: error.date, round, position });
          } else {
            setPending(null);
            notify(MESSAGES.wearFailed);
          }
        },
      },
    );
  };

  const status: TodayLooksStatus =
    wardrobeSize === 0 || wardrobeSize === 'loading'
      ? 'idle'
      : proposal
        ? 'ready'
        : (batchQuery.isPending && !batch) || (batch && resolving)
          ? 'loading'
          : batch
            ? 'empty'
            : 'error';

  return {
    status,
    proposal,
    alternatives,
    /** The batch on screen is an older one (today's could not be generated). */
    savedFromBefore: !fresh && !!batch,
    offline,
    requesting,
    wearing: wear.isPending,
    conflict: conflict !== null,
    shuffleDisabled: !unseen && (!canRequestMore || requesting),
    shuffleNote,
    shuffle,
    openAlternative: (id: string) => show(Number(id)),
    wear: () => wearCurrent(),
    confirmReplace: () =>
      conflict && wearCurrent({ outfitId: conflict.outfitId, replaceDate: conflict.date }),
    cancelReplace: () => setPending(null),
    retry: () => void batchQuery.refetch(),
  };
}
