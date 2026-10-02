import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react-native';
import { File } from 'expo-file-system';
import type { ReactNode } from 'react';
import { Platform } from 'react-native';

import { ApiError } from '../src/api-client/errors';
import { queryKeys } from '../src/api-client/query-keys';
import { usePatchGarment } from '../src/hooks/useGarmentMutations';
import { useGarment, useGarments } from '../src/hooks/useGarments';
import { useJob } from '../src/hooks/useJob';
import { useSettings } from '../src/hooks/useSettings';
import { buildUploadForm, useUploadGarment } from '../src/hooks/useUploadGarment';
import { imageUrl } from '../src/lib/image-url';

const clients: QueryClient[] = [];

function makeClient() {
  // gcTime 0 so no garbage-collection timer outlives the test.
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { gcTime: 0 } },
  });
  clients.push(client);
  return client;
}

function wrapperFor(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const fetchMock = () => globalThis.fetch as jest.Mock;
const requestAt = (n: number) => fetchMock().mock.calls[n][0] as Request;

describe('garment data layer', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = jest.fn();
  });

  afterEach(async () => {
    await cleanup();
    clients.splice(0).forEach((client) => client.clear());
    globalThis.fetch = originalFetch;
  });

  it('imageUrl prefixes the images route and is null-safe', () => {
    expect(imageUrl('cutout/abc.png')).toBe('http://localhost:8000/images/cutout/abc.png');
    expect(imageUrl(null)).toBeNull();
    expect(imageUrl(undefined)).toBeNull();
  });

  it('useGarments sends the filters and returns the list', async () => {
    fetchMock().mockResolvedValueOnce(json({ items: [], total: 0, page: 1, page_size: 50 }));
    const client = makeClient();

    const { result } = await renderHook(
      () => useGarments({ status: ['active', 'laundry'], needs_review: true }),
      { wrapper: wrapperFor(client) },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const url = new URL(requestAt(0).url);
    expect(url.pathname).toBe('/garments');
    expect(url.searchParams.getAll('status')).toEqual(['active', 'laundry']);
    expect(url.searchParams.get('needs_review')).toBe('true');
  });

  it('surfaces the error envelope message and status as ApiError', async () => {
    fetchMock().mockResolvedValueOnce(
      json(
        { error: { code: 'GARMENT_NOT_FOUND', message: 'Prenda no encontrada', details: null } },
        404,
      ),
    );

    const { result } = await renderHook(() => useGarment('g1'), {
      wrapper: wrapperFor(makeClient()),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    const error = result.current.error as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.message).toBe('Prenda no encontrada');
    expect(error.status).toBe(404);
    expect(error.code).toBe('GARMENT_NOT_FOUND');
  });

  it('falls back to a status message when the body has no envelope', async () => {
    fetchMock().mockResolvedValueOnce(new Response('', { status: 503 }));

    const { result } = await renderHook(() => useSettings(), {
      wrapper: wrapperFor(makeClient()),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as ApiError).message).toBe('Request failed with status 503');
  });

  it('useJob polls until the job is done, then stops', async () => {
    const job = (status: string, progress: number) =>
      json({ status, step: 'cutout', progress, error: null, result: null });
    fetchMock()
      .mockResolvedValueOnce(job('running', 30))
      .mockResolvedValueOnce(job('running', 60))
      .mockResolvedValueOnce(job('done', 100));

    const { result } = await renderHook(() => useJob('j1', { refetchInterval: 10 }), {
      wrapper: wrapperFor(makeClient()),
    });

    await waitFor(() => expect(result.current.data?.status).toBe('done'));
    expect(fetchMock()).toHaveBeenCalledTimes(3);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 60));
    });
    expect(fetchMock()).toHaveBeenCalledTimes(3);
  });

  it('useJob stops polling on failed', async () => {
    fetchMock().mockResolvedValue(
      json({ status: 'failed', step: 'cutout', progress: 30, error: 'Falló', result: null }),
    );

    const { result } = await renderHook(() => useJob('j1', { refetchInterval: 10 }), {
      wrapper: wrapperFor(makeClient()),
    });

    await waitFor(() => expect(result.current.data?.status).toBe('failed'));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 60));
    });
    expect(fetchMock()).toHaveBeenCalledTimes(1);
  });

  it('useJob does not fetch while disabled', async () => {
    await renderHook(() => useJob('j1', { enabled: false }), {
      wrapper: wrapperFor(makeClient()),
    });
    expect(fetchMock()).not.toHaveBeenCalled();
  });

  it('buildUploadForm appends an expo-file-system File on native', async () => {
    // expo/fetch (the native global fetch) rejects `{uri, name, type}` parts.
    const append = jest.spyOn(FormData.prototype, 'append');
    try {
      await buildUploadForm({ uri: 'file:///tmp/a.jpg', name: 'a.jpg', mimeType: 'image/jpeg' });
      const [field, part, name] = append.mock.calls[0];
      expect(field).toBe('file');
      expect(part).toBeInstanceOf(File);
      expect((part as unknown as File).uri).toBe('file:///tmp/a.jpg');
      expect(name).toBe('a.jpg');
    } finally {
      append.mockRestore();
    }
  });

  it('buildUploadForm appends a fetched Blob with the file name on web', async () => {
    const original = Platform.OS;
    Platform.OS = 'web';
    const blob = new Blob(['x'], { type: 'image/jpeg' });
    fetchMock().mockResolvedValueOnce({ blob: async () => blob });
    const append = jest.spyOn(FormData.prototype, 'append');
    try {
      await buildUploadForm({ uri: 'blob:http://x/1', name: 'a.jpg', mimeType: 'image/jpeg' });
      expect(fetchMock()).toHaveBeenCalledWith('blob:http://x/1');
      expect(append).toHaveBeenCalledWith('file', blob, 'a.jpg');
    } finally {
      append.mockRestore();
      Platform.OS = original;
    }
  });

  it('useUploadGarment posts multipart and returns the ids', async () => {
    fetchMock().mockResolvedValueOnce(json({ garment_id: 'g1', job_id: 'j1' }, 202));
    const client = makeClient();
    const invalidate = jest.spyOn(client, 'invalidateQueries');

    const { result } = await renderHook(() => useUploadGarment(), { wrapper: wrapperFor(client) });
    let created: { garment_id: string; job_id: string } | undefined;
    await act(async () => {
      created = await result.current.mutateAsync({
        uri: 'file:///tmp/a.jpg',
        name: 'a.jpg',
        mimeType: 'image/jpeg',
      });
    });

    expect(created).toEqual({ garment_id: 'g1', job_id: 'j1' });
    const request = requestAt(0);
    expect(request.method).toBe('POST');
    expect(new URL(request.url).pathname).toBe('/garments');
    expect(request.headers.get('content-type') ?? '').not.toContain('application/json');
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.garments.lists() });
  });

  it('usePatchGarment invalidates the list and the detail', async () => {
    fetchMock().mockResolvedValueOnce(json({ id: 'g1' }));
    const client = makeClient();
    const invalidate = jest.spyOn(client, 'invalidateQueries');

    const { result } = await renderHook(() => usePatchGarment('g1'), {
      wrapper: wrapperFor(client),
    });
    await act(async () => {
      await result.current.mutateAsync({ category: 'top' });
    });

    const request = requestAt(0);
    expect(request.method).toBe('PATCH');
    expect(new URL(request.url).pathname).toBe('/garments/g1');
    expect(await request.json()).toEqual({ category: 'top' });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.garments.lists() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.garments.detail('g1') });
  });
});
