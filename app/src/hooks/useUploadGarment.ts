import { useMutation, useQueryClient } from '@tanstack/react-query';
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
 * Native React Native FormData takes a `{uri, name, type}` descriptor and
 * streams the file itself; on web the URI must be fetched into a Blob first
 * because `FormData.append` only accepts Blob/File there.
 */
export async function buildUploadForm(photo: UploadPhoto): Promise<FormData> {
  const form = new FormData();
  if (Platform.OS === 'web') {
    const blob = await (await fetch(photo.uri)).blob();
    form.append('file', blob, photo.name);
  } else {
    form.append('file', { uri: photo.uri, name: photo.name, type: photo.mimeType } as never);
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
