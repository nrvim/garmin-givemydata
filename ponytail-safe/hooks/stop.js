'use strict';
// Stop: after each turn, the current session's usage numbers into the local ledger.
// Reads only the transcript Claude Code names in the hook input (and its subagents'),
// and only if it lies inside Claude Code's projects folder. Prompt text is never stored,
// unless level "developer" and `/ponytail allow names`: then the first line of the first prompt.
const path = require('path');
const lib = require('./lib');

lib.readInput((input) => {
  const cfg = lib.loadConfig();
  if (!lib.enabled(cfg, 'ledger')) return;
  const transcript = lib.safeTranscript(input.transcript_path);
  if (!transcript) {
    lib.audit(cfg, 'Stop', 'refused-transcript', { path: String(input.transcript_path || '').slice(0, 300) });
    return;
  }
  const subs = lib.subagentFiles(transcript);
  const s = lib.sessionStats([transcript, ...subs], lib.enabled(cfg, 'names'));
  const project = lib.projectDir(input);
  const session = String(input.session_id || path.basename(transcript, '.jsonl')).replace(/[^\w-]/g, '').slice(0, 64);
  lib.upsertLedger([{
    session, started: s.started || '', updated: new Date().toISOString(), project: path.basename(project),
    level: cfg.level, mode: lib.readMode(project) || 'off', model: s.model, turns: s.turns,
    input: s.input, output: s.output, cache_read: s.cacheRead, cache_write: s.cacheWrite,
    cost_usd: s.cost === null ? '' : s.cost.toFixed(4), name: s.name,
  }]);
  lib.audit(cfg, 'Stop', 'ledger', { transcript, subagents: subs.length, turns: s.turns });
});
