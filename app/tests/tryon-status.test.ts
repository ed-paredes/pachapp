import { ApiError } from '../src/api-client/errors';
import {
  notIncludedIds,
  STEP_LABELS,
  TRYON_MESSAGES,
  tryOnDescription,
  tryOnStatus,
  type TryOnRender,
} from '../src/components/today/tryon-status';
import type { LookPiece, LookRole } from '../src/components/today/types';

const piece = (garmentId: string, role: LookRole, name = garmentId): LookPiece => ({
  garmentId,
  role,
  name,
  imageUri: null,
});

const PIECES = [
  piece('p', 'bottom', 'pantalón beige'),
  piece('t', 'top', 'jersey negro'),
  piece('c', 'outerwear', 'abrigo'),
  piece('d', 'one_piece', 'vestido'),
  piece('s', 'shoes', 'botas'),
];

const render = (patch: Partial<TryOnRender> = {}): TryOnRender => ({
  id: 'r1',
  status: 'running',
  step: null,
  progress: 40,
  error: null,
  img: null,
  garment_ids: ['p', 't', 'c'],
  skipped_garment_ids: [],
  unsupported_garment_ids: [],
  created_at: '2026-10-09T10:00:00Z',
  ...patch,
});

describe('tryOnStatus steps', () => {
  it('is idle without a render or an error', () => {
    expect(tryOnStatus(undefined, PIECES)).toEqual({ phase: 'idle', progress: null, label: null });
  });

  it.each([
    ['pending', null, 0, STEP_LABELS.queued],
    ['claimed', 'loading_model', 0, STEP_LABELS.queued],
    ['running', null, 40, STEP_LABELS.queued],
    ['running', 'loading_model', 40, 'Preparando el probador…'],
    ['running', 'dressing_1', 40, 'Vistiendo la parte de abajo…'],
    ['running', 'dressing_2', 40, 'Vistiendo la parte de arriba…'],
    ['running', 'dressing_3', 40, 'Poniendo la capa de encima…'],
    ['running', 'dressing_9', 40, STEP_LABELS.dressing],
    ['running', 'finalizing', 40, 'Últimos retoques…'],
  ] as const)('%s / %s -> progress %s, "%s"', (status, step, progress, label) => {
    expect(tryOnStatus(render({ status, step }), PIECES)).toEqual({
      phase: 'working',
      progress,
      label,
    });
  });

  it('labels mid_layer and one_piece passes by the garment of that pass', () => {
    const pieces = [piece('m', 'mid_layer'), piece('d', 'one_piece')];
    const base = { status: 'running' as const, garment_ids: ['d', 'm'] };
    expect(tryOnStatus(render({ ...base, step: 'dressing_1' }), pieces).label).toBe(
      'Vistiendo la prenda entera…',
    );
    expect(tryOnStatus(render({ ...base, step: 'dressing_2' }), pieces).label).toBe(
      'Poniendo la capa de encima…',
    );
  });

  it('is done at 100 with an image', () => {
    expect(tryOnStatus(render({ status: 'done', img: 'tryon/r1.webp' }), PIECES)).toEqual({
      phase: 'done',
      progress: 100,
      label: null,
    });
  });
});

describe('tryOnStatus errors', () => {
  const failed = (error: string | null) => render({ status: 'failed', error });
  const asError = (kind: string, message: string) => ({
    phase: 'error',
    progress: null,
    label: null,
    errorKind: kind,
    message,
  });

  it.each(['out_of_memory', 'engine_unavailable', 'engine_error', 'interrupted', 'blank_output'])(
    'polled transient %s -> retry',
    (code) => {
      expect(tryOnStatus(failed(code), PIECES)).toEqual(asError('retry', TRYON_MESSAGES.retry));
    },
  );

  it('a transient failure returned by the POST (capped or cooling down) -> later', () => {
    expect(tryOnStatus(failed('engine_error'), PIECES, { fromRequest: true })).toEqual(
      asError('later', TRYON_MESSAGES.later),
    );
  });

  it.each([
    ['garment_changed', 'retry', TRYON_MESSAGES.garmentChanged],
    ['garment_missing', 'final', TRYON_MESSAGES.garmentImage],
    ['invalid_garment', 'final', TRYON_MESSAGES.garmentImage],
    ['invalid_params', 'final', TRYON_MESSAGES.generic],
    ['mannequin_unavailable', 'final', TRYON_MESSAGES.generic],
    ['something_new', 'final', TRYON_MESSAGES.generic],
    [null, 'final', TRYON_MESSAGES.generic],
  ])('render error %s -> %s', (code, kind, message) => {
    expect(tryOnStatus(failed(code), PIECES, { fromRequest: true })).toEqual(
      asError(kind, message),
    );
  });

  it.each([
    ['TRYON_GARMENT_IMAGE_MISSING', 'final', TRYON_MESSAGES.garmentImage],
    ['TRYON_GARMENT_NOT_READY', 'later', TRYON_MESSAGES.garmentNotReady],
    ['TRYON_NO_COMPATIBLE_GARMENTS', 'final', TRYON_MESSAGES.noCompatible],
    ['TRYON_DISABLED', 'final', TRYON_MESSAGES.disabled],
    ['OTHER', 'final', TRYON_MESSAGES.generic],
  ])('request ApiError %s -> %s', (code, kind, message) => {
    const error = new ApiError('x', 422, code);
    expect(tryOnStatus(undefined, PIECES, { error })).toEqual(asError(kind, message));
  });

  it('a network failure -> retry with the connection copy', () => {
    expect(
      tryOnStatus(undefined, PIECES, { error: new TypeError('Network request failed') }),
    ).toEqual(asError('retry', TRYON_MESSAGES.network));
  });
});

describe('not included and description', () => {
  it('joins unsupported and skipped ids without repeats', () => {
    const r = render({ unsupported_garment_ids: ['s', 'a'], skipped_garment_ids: ['a', 'k'] });
    expect(notIncludedIds(r)).toEqual(['s', 'a', 'k']);
    expect(notIncludedIds(undefined)).toEqual([]);
  });

  it('describes the dressed pieces by name, outermost first, in lower case', () => {
    expect(tryOnDescription(render({ garment_ids: ['p', 't'] }), PIECES)).toBe(
      'Outfit puesto en un modelo: jersey negro, pantalón beige',
    );
    expect(tryOnDescription(render({ garment_ids: ['p', 'c', 't'] }), PIECES)).toBe(
      'Outfit puesto en un modelo: abrigo, jersey negro, pantalón beige',
    );
    const named = [piece('a', 'top', 'Polo shirt marrón'), piece('b', 'bottom', 'Trousers negros')];
    expect(tryOnDescription(render({ garment_ids: ['b', 'a'] }), named)).toBe(
      'Outfit puesto en un modelo: polo shirt marrón, trousers negros',
    );
    expect(tryOnDescription(render({ garment_ids: ['zz'] }), PIECES)).toBe(
      'Outfit puesto en un modelo',
    );
  });
});
