// Runs after the test framework is installed, so RNTL can register cleanup.
// `findBy*`/`waitFor` default to 1 s, which a cold screen render can exceed on
// a checkout under /mnt/* (WSL reading the Windows disk); allow 5 s.
const { configure } = require('@testing-library/react-native');

configure({ asyncUtilTimeout: 5000 });

// On device, expo-file-system's `File` is Blob-like and expo/fetch reads it
// through `bytes()`; Node's FormData only accepts real Blobs, so tests get a
// Blob subclass that keeps the `uri`.
jest.mock('expo-file-system', () => ({
  File: class MockFile extends Blob {
    constructor(uri) {
      super(['photo'], { type: 'image/jpeg' });
      this.uri = uri;
    }
  },
}));
