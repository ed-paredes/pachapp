import type { components } from '@/api-client/schema';
import type { PillTone } from '@/components/ui';
import type { QueueItem } from '@/hooks/useUploadQueue';

type Job = Pick<components['schemas']['JobRead'], 'status' | 'step' | 'progress'>;

export const STEP_LABELS: Record<string, string> = {
  preprocess: 'Preparando',
  cutout: 'Recortando',
  color: 'Analizando colores',
  ai_attributes: 'Analizando prenda',
  embedding: 'Calculando similitud',
  consolidate: 'Terminando',
};

export type UploadStatus = {
  kind: 'uploading' | 'queued' | 'analysing' | 'done' | 'failed';
  /** State pill text. */
  label: string;
  tone: PillTone;
  /** Line under the name: what is happening right now. `null` once there is nothing to say. */
  step: string | null;
  /** 0-100 when the server reports it, `null` while unknown (upload in flight). */
  progress: number | null;
};

/**
 * Maps a queue item and its polled job to what the card shows: the pill (Subiendo / En cola /
 * Analizando / Lista / Error), the step line and the bar value. Pure, so it is unit-tested.
 */
export function uploadStatus(phase: QueueItem['phase'], job?: Job | null): UploadStatus {
  if (phase === 'error') {
    return { kind: 'failed', label: 'Error', tone: 'warn', step: null, progress: null };
  }
  if (phase === 'preparing' || phase === 'uploading') {
    return {
      kind: 'uploading',
      label: 'Subiendo',
      tone: 'info',
      step: phase === 'preparing' ? 'Preparando la foto' : 'Subiendo la foto',
      progress: null,
    };
  }
  if (job?.status === 'done') {
    return { kind: 'done', label: 'Lista', tone: 'ok', step: null, progress: 100 };
  }
  if (job?.status === 'failed') {
    return { kind: 'failed', label: 'Error', tone: 'warn', step: null, progress: null };
  }
  if (job?.status === 'running') {
    return {
      kind: 'analysing',
      label: 'Analizando',
      tone: 'info',
      step: (job.step && STEP_LABELS[job.step]) || 'Procesando',
      progress: job.progress,
    };
  }
  return { kind: 'queued', label: 'En cola', tone: 'ghost', step: 'Esperando turno', progress: 0 };
}
