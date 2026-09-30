/** @type {import('jest').Config} */
module.exports = {
  preset: 'jest-expo',
  testMatch: ['<rootDir>/tests/**/*.test.[jt]s?(x)'],
  setupFiles: ['<rootDir>/jest.setup.js'],
  setupFilesAfterEnv: ['<rootDir>/jest.setup-after-env.js'],
  // The first screen test of a suite pays the module load; on a checkout under
  // /mnt/* (WSL reading the Windows disk) that alone exceeds Jest's 5 s default.
  testTimeout: 20000,
};
