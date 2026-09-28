describe('api-client config', () => {
  const ORIGINAL_ENV = process.env.EXPO_PUBLIC_API_BASE_URL;

  afterEach(() => {
    if (ORIGINAL_ENV === undefined) {
      delete process.env.EXPO_PUBLIC_API_BASE_URL;
    } else {
      process.env.EXPO_PUBLIC_API_BASE_URL = ORIGINAL_ENV;
    }
    jest.resetModules();
  });

  it('returns the env value when set', () => {
    jest.resetModules();
    process.env.EXPO_PUBLIC_API_BASE_URL = 'http://192.168.1.10:8000';

    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { API_BASE_URL } = require('@/api-client/config');

    expect(API_BASE_URL).toBe('http://192.168.1.10:8000');
  });

  it('throws a clear error when unset', () => {
    jest.resetModules();
    delete process.env.EXPO_PUBLIC_API_BASE_URL;

    expect(() => {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      require('@/api-client/config');
    }).toThrow('EXPO_PUBLIC_API_BASE_URL');
  });
});
