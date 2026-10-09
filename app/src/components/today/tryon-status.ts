import { ApiError, isNetworkError } from '@/api-client/errors';
import type { components } from '@/api-client/schema';

import type { LookPiece, LookRole } from './types';

/** The render as `GET /tryon/{id}` and `POST /tryon` return it. */
export type TryOnRender = components['schemas']['TryOnRead'];

export type TryOnPhase = 'idle' | 'working' | 'done' | 'error';

/**
 * What the user can do about an error: `retry` (try again now), `later` (the backend needs time),
 * `final` (trying again will not help until something else changes).
 */
export type TryOnErrorKind = 'retry' | 'later' | 'final';

export type TryOnStatus = {
  phase: TryOnPhase;
  /** 0-100 while working, `null` when unknown (nothing reported yet). */
  progress: number | null;
  /** Step line while working; `null` otherwise. */
  label: string | null;
  errorKind?: TryOnErrorKind;
  /** Error text, set with `errorKind`. */
  message?: string;
};

export type TryOnStatusOptions = {
  /** The failure of the request (`POST /tryon`) or of the poll, when that is what failed. */
  error?: unknown;
  /**
   * The render came back from the `POST` itself (HTTP 200), not from polling. A transient failure
   * arriving that way means the retry cap or the cooldown stopped the resubmit.
   */
  fromRequest?: boolean;
};

export const STEP_LABELS = {
  queued: 'En cola…',
  loading_model: 'Preparando el probador…',
  finalizing: 'Últimos retoques…',
  /** A `dressing_N` step whose garment cannot be resolved. */
  dressing: 'Vistiendo el look…',
} as const;

const DRESSING_LABELS: Partial<Record<LookRole, string>> = {
  bottom: 'Vistiendo la parte de abajo…',
  top: 'Vistiendo la parte de arriba…',
  mid_layer: 'Poniendo la capa de encima…',
  outerwear: 'Poniendo la capa de encima…',
  one_piece: 'Vistiendo la prenda entera…',
};

/** Shown under the progress while a render is working. */
export const TRYON_HELPER = 'Puede tardar alrededor de un minuto. Puedes seguir usando la app.';

export const TRYON_MESSAGES = {
  retry: 'No pudimos probar este look. Inténtalo de nuevo.',
  later: 'Lo intentamos varias veces sin suerte. Vuelve a probar en unos minutos.',
  garmentChanged: 'Una prenda cambió desde la última prueba. Inténtalo de nuevo.',
  garmentImage: 'A una prenda le falta la imagen o no se puede usar. Revisa su foto en el armario.',
  garmentNotReady: 'Una prenda todavía se está procesando. Vuelve a probar en un momento.',
  noCompatible: 'Este look no tiene prendas que podamos probar en el modelo.',
  disabled: 'La prueba virtual no está disponible ahora mismo.',
  generic: 'No pudimos preparar este look.',
  network: 'Sin conexión con el servidor. Comprueba la conexión e inténtalo de nuevo.',
} as const;

/** Failures a new attempt may fix; the worker retries them up to its cap. */
const TRANSIENT_CODES = new Set([
  'out_of_memory',
  'engine_unavailable',
  'engine_error',
  'interrupted',
  'blank_output',
]);

type ErrorStatus = Required<Pick<TryOnStatus, 'errorKind' | 'message'>>;

/** Maps a render `error` code or an `ApiError` code to what the user sees. Unknown codes are final. */
function errorFor(code: string | null, fromRequest: boolean): ErrorStatus {
  if (code && TRANSIENT_CODES.has(code)) {
    return fromRequest
      ? { errorKind: 'later', message: TRYON_MESSAGES.later }
      : { errorKind: 'retry', message: TRYON_MESSAGES.retry };
  }
  switch (code) {
    case 'garment_changed':
      return { errorKind: 'retry', message: TRYON_MESSAGES.garmentChanged };
    case 'garment_missing':
    case 'invalid_garment':
    case 'TRYON_GARMENT_IMAGE_MISSING':
      return { errorKind: 'final', message: TRYON_MESSAGES.garmentImage };
    case 'TRYON_GARMENT_NOT_READY':
      return { errorKind: 'later', message: TRYON_MESSAGES.garmentNotReady };
    case 'TRYON_NO_COMPATIBLE_GARMENTS':
      return { errorKind: 'final', message: TRYON_MESSAGES.noCompatible };
    case 'TRYON_DISABLED':
      return { errorKind: 'final', message: TRYON_MESSAGES.disabled };
    default:
      // invalid_params, mannequin_unavailable and anything the app does not know.
      return { errorKind: 'final', message: TRYON_MESSAGES.generic };
  }
}

function stepLabel(render: TryOnRender, pieces: LookPiece[]): string {
  const step = render.step ?? '';
  if (step === 'loading_model') return STEP_LABELS.loading_model;
  if (step === 'finalizing') return STEP_LABELS.finalizing;
  const dressing = /^dressing_(\d+)$/.exec(step);
  if (dressing) {
    // `garment_ids` are in pass order, so the N-th pass dresses the N-th id.
    const id = render.garment_ids[Number(dressing[1]) - 1];
    const role = pieces.find((piece) => piece.garmentId === id)?.role;
    return (role && DRESSING_LABELS[role]) || STEP_LABELS.dressing;
  }
  return STEP_LABELS.queued;
}

/**
 * Maps a render (and the failure of its request, if any) to what the look canvas shows: the phase,
 * the bar value, the step line and, on errors, the kind and text. Pure, so it is unit-tested.
 */
export function tryOnStatus(
  render: TryOnRender | null | undefined,
  pieces: LookPiece[],
  { error, fromRequest = false }: TryOnStatusOptions = {},
): TryOnStatus {
  if (error !== undefined && error !== null) {
    if (isNetworkError(error)) {
      return {
        phase: 'error',
        progress: null,
        label: null,
        errorKind: 'retry',
        message: TRYON_MESSAGES.network,
      };
    }
    const code = error instanceof ApiError ? error.code : null;
    return { phase: 'error', progress: null, label: null, ...errorFor(code, false) };
  }
  if (!render) return { phase: 'idle', progress: null, label: null };
  if (render.status === 'done') return { phase: 'done', progress: 100, label: null };
  if (render.status === 'failed') {
    return {
      phase: 'error',
      progress: null,
      label: null,
      ...errorFor(render.error, fromRequest),
    };
  }
  const queued = render.status === 'pending' || render.status === 'claimed';
  return {
    phase: 'working',
    progress: queued ? 0 : render.progress,
    label: queued ? STEP_LABELS.queued : stepLabel(render, pieces),
  };
}

/** Garments the image does not show: the ones the engine cannot dress plus the ones it skipped. */
export function notIncludedIds(render: TryOnRender | null | undefined): string[] {
  if (!render) return [];
  return [...new Set([...render.unsupported_garment_ids, ...render.skipped_garment_ids])];
}

const DESCRIBE_ORDER: LookRole[] = ['outerwear', 'mid_layer', 'top', 'one_piece', 'bottom'];

const describeRank = (role: LookRole) => {
  const rank = DESCRIBE_ORDER.indexOf(role);
  return rank < 0 ? DESCRIBE_ORDER.length : rank;
};

/** Screen reader text of the result: 'Outfit puesto en un modelo: jersey negro, pantalón beige'. */
export function tryOnDescription(
  render: TryOnRender | null | undefined,
  pieces: LookPiece[],
): string {
  const worn = (render?.garment_ids ?? [])
    .map((id) => pieces.find((piece) => piece.garmentId === id))
    .filter((piece): piece is LookPiece => !!piece);
  // Outermost first, whatever the order the passes ran in; the sort is stable within a role.
  const names = worn
    .sort((a, b) => describeRank(a.role) - describeRank(b.role))
    .map((piece) => piece.name.charAt(0).toLowerCase() + piece.name.slice(1));
  return names.length > 0
    ? `Outfit puesto en un modelo: ${names.join(', ')}`
    : 'Outfit puesto en un modelo';
}
