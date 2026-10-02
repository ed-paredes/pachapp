import { useMutation, useQueryClient } from '@tanstack/react-query';
import { File } from 'expo-file-system';
import { Platform } from 'react-native';

import { unwrap } from '@/api-client/errors';
import { apiClient } from '@/api-client/http-client';
import { queryKeys } from '@/api-client/query-keys';

export type UploadPhoto = {
  /** Local `file://` URI (native) or `blob:`/`data:` URI (web). */
  uri: string;
  name: string;
  mimeType: string;
};

/**
 * Builds the multipart body for `POST /garments` (field `file`).
 * On native the global `fetch` is `expo/fetch`, which only serialises
 * Blob-like parts (it rejects React Native's `{uri, name, type}` descriptor),
 * so the photo goes in as an `expo-file-system` `File`. On web the URI must
 * be fetched into a Blob first because `FormData.append` only accepts
 * Blob/File there.
 */
export async function buildUploadForm(photo: UploadPhoto): Promise<FormData> {
  const form = new FormData();
  if (Platform.OS === 'web') {
    const blob = await (await fetch(photo.uri)).blob();
    form.append('file', blob, photo.name);
  } else {
    form.append('file', new File(photo.uri) as unknown as Blob, photo.name);
  }
  return form;
}

/** `POST /garments` (202): returns `{garment_id, job_id}`. */
export function useUploadGarment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (photo: UploadPhoto) => {
      const body = await buildUploadForm(photo);
      return unwrap(
        await apiClient.POST('/garments', {
          // The generated type says `{file: string}`; the default body
          // serializer passes FormData through untouched.
          body: body as unknown as { file: string },
        }),
      );
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.garments.lists() }),
  });
}
