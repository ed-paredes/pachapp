/**
 * Base URL of the pachapp backend API, read from the environment.
 *
 * Required per docs/specs/01-dev-tooling.md (`EXPO_PUBLIC_API_BASE_URL`): the
 * app must point at the API's LAN-reachable `host:port`. There is no
 * versioned default — startup must fail fast and clearly if it is missing,
 * matching the backend's fail-fast behavior for required settings.
 */
function readApiBaseUrl(): string {
  const value = process.env.EXPO_PUBLIC_API_BASE_URL;
  if (!value) {
    throw new Error(
      'EXPO_PUBLIC_API_BASE_URL is not set. Define it in app/.env (or your shell) ' +
        'pointing at the backend API, e.g. EXPO_PUBLIC_API_BASE_URL=http://192.168.1.10:8000',
    );
  }
  return value;
}

export const API_BASE_URL = readApiBaseUrl();
