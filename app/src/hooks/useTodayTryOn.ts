import { useCallback, useMemo, useState } from 'react';

import type { TodayTryOn } from '@/components/today/TryOnLayer';
import type { LookPiece } from '@/components/today/types';
import { GARMENT_FIXABLE_ERRORS } from '@/components/today/tryon-status';
import { imageUrl } from '@/lib/image-url';

import { lookKey, useLookTryOn } from './useTryOn';
import { isLookTryable, useTryOnCapabilities } from './useTryOnCapabilities';

type View = 'collage' | 'tryon';

/**
 * The try-on of the look on Hoy: the button state, the Collage | Puesto choice and the canvas
 * data. The choice is remembered per look (a look opens in "Collage"; one that already has a
 * finished render opens in "Puesto"), so shuffling and coming back keeps what the user picked.
 */
export function useTodayTryOn(pieces: LookPiece[] | undefined, offline: boolean): TodayTryOn {
  const list = useMemo(() => pieces ?? [], [pieces]);
  const ids = useMemo(() => list.map((piece) => piece.garmentId), [list]);
  const key = lookKey(ids);
  const capabilities = useTryOnCapabilities();
  const tryOn = useLookTryOn(ids, list);
  const [choices, setChoices] = useState<Record<string, View>>({});

  const { status, render, request } = tryOn;
  const tried = status.phase !== 'idle';
  const requested: View = status.phase === 'done' ? 'tryon' : 'collage';
  // Nothing to show on "Puesto" for a look without a render.
  const mode: View = tried ? (choices[key] ?? requested) : 'collage';
  const setMode = useCallback(
    (next: View) => setChoices((prev) => ({ ...prev, [key]: next })),
    [key],
  );

  // A render that failed for good: asking again returns the same failure, so the button waits
  // for something to change (another look; or, for a garment problem, the garment).
  const deadEnd =
    render?.status === 'failed' &&
    status.errorKind === 'final' &&
    !GARMENT_FIXABLE_ERRORS.has(render.error ?? '');

  const onTryOn = useCallback(() => {
    setMode('tryon');
    // A render that exists (working, done) is just shown; only a look without one, or a failed one, is requested.
    if (status.phase === 'idle' || status.phase === 'error') request();
  }, [setMode, status.phase, request]);

  const notIncluded = useMemo(
    () => tryOn.notIncluded.flatMap((id) => list.find((piece) => piece.garmentId === id) ?? []),
    [tryOn.notIncluded, list],
  );

  return {
    canTry: isLookTryable(list, capabilities.data),
    // Offline a render can only be viewed, not made.
    tryOnDisabled:
      status.phase === 'working' ||
      tryOn.isRequesting ||
      deadEnd ||
      (offline && status.phase !== 'done'),
    onTryOn,
    showToggle: tried,
    mode,
    onModeChange: setMode,
    canvas: {
      mode,
      status,
      imageUri: imageUrl(render?.img),
      description: tryOn.description,
      onRetry: request,
      onShowCollage: () => setMode('collage'),
    },
    notIncluded,
  };
}
