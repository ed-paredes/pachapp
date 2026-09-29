// Provide a default API base URL for tests that don't care about it, so
// importing `@/api-client/config` (and anything built on it) doesn't throw.
// Tests that specifically exercise that fail-fast behavior manage the env
// var themselves (see tests/api-client-config.test.ts).
if (!process.env.EXPO_PUBLIC_API_BASE_URL) {
  process.env.EXPO_PUBLIC_API_BASE_URL = 'http://localhost:8000';
}
