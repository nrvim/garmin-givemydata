'use strict';
// Starts one Ponytail Safe hook inside Node's sandbox. The hook command is only
//   node "${CLAUDE_PLUGIN_ROOT}/hooks/launch.js" <hook>
// so it works the same in bash, PowerShell and cmd: no shell expands any path. The folders a
// hook may read and write are worked out here, with the same functions the hooks use, so the
// sandbox and the code can never point at different folders (they did on Windows).
//
// This file is the only Ponytail Safe code that uses child_process, and only to start this
// same Node binary with --permission and a fixed script. It never reads the hook's input:
// stdin, stdout and stderr go straight through to the sandboxed hook.
const { spawnSync } = require('child_process');
const path = require('path');
const lib = require('./lib');

// Per hook: the script, what it may read (besides the plugin itself), whether it may write
// Ponytail Safe's own folder, and a time limit just under the hook timeout in hooks.json.
const HOOKS = {
  'session-start': { script: 'session-start.js', read: ['data', 'project'], write: true, ms: 9000 },
  prompt: { script: 'prompt.js', read: ['data', 'transcripts'], write: true, ms: 28000 },
  subagent: { script: 'subagent.js', read: ['data'], write: false, ms: 9000 },
  stop: { script: 'stop.js', read: ['data', 'transcripts'], write: true, ms: 14000 },
  guard: { script: 'guard.js', read: [], write: false, ms: 4000 },
};

const FOLDERS = {
  data: () => lib.dataDir(),
  transcripts: () => lib.projectsDir(),
  project: () => lib.projectDir(),
};

// A folder and everything below it, also when it does not exist yet: Node needs the trailing *.
const tree = (dir) => path.join(dir, '*');

function flagsFor(name) {
  const h = HOOKS[name];
  if (!h) return null;
  const flags = ['--permission', '--allow-fs-read=' + tree(lib.pluginRoot())];
  for (const f of h.read) flags.push('--allow-fs-read=' + tree(FOLDERS[f]()));
  if (h.write) flags.push('--allow-fs-write=' + tree(lib.dataDir()));
  return { flags, script: path.join(__dirname, h.script), ms: h.ms };
}

if (require.main === module) {
  const run = flagsFor(process.argv[2]);
  if (!run) process.exit(0); // unknown hook name: do nothing
  const r = spawnSync(process.execPath, [...run.flags, run.script], { stdio: 'inherit', timeout: run.ms, windowsHide: true });
  // A hook that fails or times out never blocks the session.
  process.exit(r.status === null ? 0 : r.status);
}

module.exports = { HOOKS, flagsFor };
