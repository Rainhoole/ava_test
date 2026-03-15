const os = require('os');

// Vercel CLI currently builds an OAuth user-agent string with os.hostname().
// On this Windows machine the hostname contains non-ASCII characters, which
// breaks the HTTP header during login. Force an ASCII hostname for this process.
os.hostname = () => 'ava-local';
