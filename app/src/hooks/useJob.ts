import { useQuery } from '@tanstack/react-query';

import { unwrap } from '@/api-client/errors';
import { apiClient } from '@/api-client/http-client';
import { queryKeys } from '@/api-client/query-keys';

/** Default polling interval for `GET /jobs/{id}` (UI-REQ-017). */
export const JOB_POLL_INTERVAL_MS = 1000;

type UseJobOptions = {
  enabled?: boolean;
  /** Polling interval in ms while the job is not done/failed. */
  refetchInterval?: number;
};

/**
 * `GET /jobs/{id}`, polled until the job is `done` or `failed` (UI-REQ-017).
 * Each job id has its own query, so concurrent uploads poll independently
 * (UI-REQ-018). A retry that puts the job back to pending resumes polling as
 * soon as the query is refetched (`useRetryGarment` invalidates it).
 */
export function useJob(id: string | undefined, options: UseJobOptions = {}) {
  const { enabled = true, refetchInterval = JOB_POLL_INTERVAL_MS } = options;
  return useQuery({
    queryKey: queryKeys.jobs.detail(id ?? ''),
    enabled: enabled && !!id,
    queryFn: async () =>
      unwrap(await apiClient.GET('/jobs/{job_id}', { params: { path: { job_id: id as string } } })),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'done' || status === 'failed' ? false : refetchInterval;
    },
  });
}
