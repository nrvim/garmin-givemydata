'use strict';
// SessionStart: injects the ruleset for the default mode. The codebase map only with level
// "controlled" or higher AND the user's `/ponytail allow map`. Never touches Claude Code settings.
const lib = require('./lib');
const { buildMap } = require('./map');

lib.readInput((input) => {
  const cfg = lib.loadConfig();
  const project = lib.projectDir(input);
  // Compaction re-runs SessionStart inside the same conversation: keep the live mode.
  const mode = input.source === 'compact' ? (lib.readMode(project) || 'off') : cfg.defaultMode;
  if (mode === 'off') {
    lib.clearMode(project);
    lib.audit(cfg, 'SessionStart', 'off');
    return;
  }
  try { lib.setMode(project, mode, cfg); } catch (e) { /* mode file is best-effort */ }
  let text = lib.instructions(mode, cfg);
  if (lib.enabled(cfg, 'map')) {
    const map = buildMap(project);
    if (map.text) text += '\n\n' + map.text;
    lib.audit(cfg, 'SessionStart', 'map', { root: project, filesRead: map.files });
  }
  lib.audit(cfg, 'SessionStart', 'ruleset', { mode, source: String(input.source || '') });
  lib.output('SessionStart', text);
});
