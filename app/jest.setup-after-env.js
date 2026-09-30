// Runs after the test framework is installed, so RNTL can register cleanup.
// `findBy*`/`waitFor` default to 1 s, which a cold screen render can exceed on
// a checkout under /mnt/* (WSL reading the Windows disk); allow 5 s.
const { configure } = require('@testing-library/react-native');

configure({ asyncUtilTimeout: 5000 });
