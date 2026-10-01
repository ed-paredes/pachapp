import { useCallback, useRef, useState } from 'react';

import { ApiError } from '@/api-client/errors';
import { isLowResolution, preparePhoto, type PickedAsset } from '@/lib/photos';

import { useUploadGarment, type UploadPhoto } from './useUploadGarment';

export type QueueItem = {
  key: string;
  name: string;
  /** `preparing`/`uploading` are local; `queued` means the server owns it (poll `jobId`). */
  phase: 'preparing' | 'uploading' | 'queued' | 'error';
  garmentId?: string;
  jobId?: string;
  error?: string;
  /** The picked photo is small (long side < 800 px); upload still proceeds. */
  lowRes?: boolean;
  /** Local URI of the picked photo, shown as a preview until the cutout exists. */
  previewUri?: string;
  /** Prepared photo, kept so a failed upload can be retried. */
  photo?: UploadPhoto;
};

const NETWORK_ERROR = 'No se pudo subir la foto. Comprueba la conexión e inténtalo de nuevo.';

function messageFor(error: unknown): string {
  return error instanceof ApiError ? error.message : NETWORK_ERROR;
}

/**
 * In-memory queue of photos on Añadir (UI-REQ-006/018). Every photo is
 * resized and uploaded independently, so the user can add more while earlier
 * ones are still uploading or processing. Server-side progress is polled per
 * item by `UploadItem` via `useJob`. Not persisted across app restarts.
 */
export function useUploadQueue() {
  const upload = useUploadGarment();
  const [items, setItems] = useState<QueueItem[]>([]);
  const counter = useRef(0);

  const patch = useCallback((key: string, changes: Partial<QueueItem>) => {
    setItems((current) =>
      current.map((item) => (item.key === key ? { ...item, ...changes } : item)),
    );
  }, []);

  const send = useCallback(
    async (key: string, photo: UploadPhoto) => {
      patch(key, { phase: 'uploading', error: undefined, photo });
      try {
        const created = await upload.mutateAsync(photo);
        patch(key, {
          phase: 'queued',
          garmentId: created.garment_id,
          jobId: created.job_id,
          photo: undefined,
        });
      } catch (error) {
        patch(key, { phase: 'error', error: messageFor(error) });
      }
    },
    [patch, upload],
  );

  const addAssets = useCallback(
    (assets: PickedAsset[]) => {
      assets.forEach((asset, index) => {
        counter.current += 1;
        const key = `photo-${counter.current}`;
        const name = asset.fileName ?? `Foto ${counter.current}`;
        setItems((current) => [
          ...current,
          { key, name, phase: 'preparing', lowRes: isLowResolution(asset), previewUri: asset.uri },
        ]);
        void (async () => {
          try {
            await send(key, await preparePhoto(asset, index));
          } catch {
            patch(key, { phase: 'error', error: 'No se pudo preparar la foto.' });
          }
        })();
      });
    },
    [patch, send],
  );

  const retryUpload = useCallback(
    (key: string) => {
      const item = items.find((candidate) => candidate.key === key);
      if (item?.photo) {
        void send(key, item.photo);
      }
    },
    [items, send],
  );

  const dismiss = useCallback((key: string) => {
    setItems((current) => current.filter((item) => item.key !== key));
  }, []);

  return { items, addAssets, retryUpload, dismiss };
}
