import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import * as ImagePicker from 'expo-image-picker';

import type { UploadPhoto } from '@/hooks/useUploadGarment';

/** Longest side sent to the server (default `upload_max_px`, 03-garment-ingestion). */
export const MAX_UPLOAD_PX = 2048;

/** Photos whose long side is below this look blurry once cut out and shown large. */
export const LOW_RES_PX = 800;

export const LOW_RES_NOTE =
  'Foto de baja resolución: se verá borrosa. Mejor una foto más cercana y con más luz.';

export function isLowResolution(asset: Pick<PickedAsset, 'width' | 'height'>): boolean {
  const longSide = Math.max(asset.width, asset.height);
  return longSide > 0 && longSide < LOW_RES_PX;
}

export const CAMERA_DENIED_MESSAGE =
  'Necesitamos permiso para usar la cámara. Actívalo en los ajustes del dispositivo.';

export type PickedAsset = { uri: string; width: number; height: number; fileName?: string | null };

export type PickResult =
  | { kind: 'assets'; assets: PickedAsset[] }
  | { kind: 'canceled' }
  | { kind: 'denied'; message: string };

/**
 * Opens the camera (UI-REQ-013). On web `expo-image-picker` falls back to the
 * browser's capture file input, which needs no permission.
 */
export async function pickFromCamera(): Promise<PickResult> {
  const permission = await ImagePicker.requestCameraPermissionsAsync();
  if (!permission.granted) {
    return { kind: 'denied', message: CAMERA_DENIED_MESSAGE };
  }
  const result = await ImagePicker.launchCameraAsync({ mediaTypes: ['images'] });
  return result.canceled ? { kind: 'canceled' } : { kind: 'assets', assets: result.assets };
}

/** Opens the gallery (native) or the file input (web), multi-select. */
export async function pickFromGallery(): Promise<PickResult> {
  const result = await ImagePicker.launchImageLibraryAsync({
    mediaTypes: ['images'],
    allowsMultipleSelection: true,
  });
  return result.canceled ? { kind: 'canceled' } : { kind: 'assets', assets: result.assets };
}

/**
 * Re-encodes a picked photo as JPEG (which also normalises HEIC and EXIF
 * orientation) and scales it so its long side is at most `MAX_UPLOAD_PX`.
 */
export async function preparePhoto(asset: PickedAsset, index = 0): Promise<UploadPhoto> {
  const context = ImageManipulator.manipulate(asset.uri);
  const longSide = Math.max(asset.width, asset.height);
  if (longSide > MAX_UPLOAD_PX) {
    context.resize(
      asset.width >= asset.height ? { width: MAX_UPLOAD_PX } : { height: MAX_UPLOAD_PX },
    );
  }
  const image = await context.renderAsync();
  const saved = await image.saveAsync({ format: SaveFormat.JPEG, compress: 0.9 });
  const base = (asset.fileName ?? `foto-${Date.now()}-${index}`).replace(/\.[^./\\]+$/, '');
  return { uri: saved.uri, name: `${base}.jpg`, mimeType: 'image/jpeg' };
}
