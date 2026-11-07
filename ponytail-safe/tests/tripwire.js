'use strict';
// Test-only preload: any network or subprocess attempt by a hook is reported on stderr and blocked.
const report = (what) => { try { process.stderr.write('TRIPWIRE:' + what + '\n'); } catch (e) {} throw new Error('blocked by tripwire: ' + what); };
const patch = (mod, names) => { const m = require(mod); for (const n of names) if (typeof m[n] === 'function') m[n] = () => report(mod + '.' + n); };
patch('net', ['connect', 'createConnection', 'createServer']);
patch('tls', ['connect', 'createServer']);
patch('http', ['request', 'get', 'createServer']);
patch('https', ['request', 'get', 'createServer']);
patch('http2', ['connect', 'createServer']);
patch('dgram', ['createSocket']);
patch('dns', ['lookup', 'resolve', 'resolve4', 'resolve6']);
// hooks/launch.js runs outside the sandbox and must start the sandboxed hook; every hook itself
// runs with process.permission set, and there any subprocess attempt is a finding.
if (process.permission) patch('child_process', ['spawn', 'spawnSync', 'exec', 'execSync', 'execFile', 'execFileSync', 'fork']);
require('net').Socket.prototype.connect = () => report('net.Socket.connect');
globalThis.fetch = () => report('fetch');
globalThis.WebSocket = function () { report('WebSocket'); };
