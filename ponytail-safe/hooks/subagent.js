'use strict';
// SubagentStart: the same ruleset for subagents while ponytail is on. Reads only its own config.
const lib = require('./lib');

lib.readInput((input) => {
  const cfg = lib.loadConfig();
  const mode = lib.readMode(lib.projectDir(input));
  if (!mode || mode === 'off' || !lib.enabled(cfg, 'subagents')) return;
  lib.audit(cfg, 'SubagentStart', 'ruleset', { mode, agent: String(input.agent_type || '').slice(0, 60) });
  lib.output('SubagentStart', lib.instructions(mode, cfg));
});
