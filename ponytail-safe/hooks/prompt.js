'use strict';
// UserPromptSubmit: the only place a level or a permission can change, because only a prompt the
// user typed reaches this hook. The whole prompt must be the command (`/ponytail allow map`), so a
// sentence that merely mentions it, or text pasted from a file or web page inside a longer prompt,
// changes nothing. Prompt text is never stored or logged.
const fs = require('fs');
const path = require('path');
const lib = require('./lib');

const CMD = /^\/(?:ponytail-safe:)?ponytail(?:\s+([\s\S]*))?$/i;
const STOP = /^(stop ponytail|normal mode)[.!?\s]*$/i;
const IMPORT_MS = 20000;

function featureTable(cfg) {
  return Object.entries(lib.FEATURES).map(([name, f]) => {
    const state = lib.enabled(cfg, name) ? 'ON '
      : !lib.levelAllows(cfg.level, name) ? `off (needs level ${f.level})`
        : f.consent ? 'off (needs /ponytail allow ' + name + ')' : 'off (denied)';
    return `  ${name.padEnd(10)} ${state.padEnd(36)} ${f.desc}`;
  }).join('\n');
}

const money = (n) => `$${n.toFixed(2)}`;
const kTokens = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : String(n));

function dashboard(cfg, project) {
  const rows = lib.readLedger();
  const sum = (list, f) => list.reduce((a, r) => a + (Number(r[f]) || 0), 0);
  const mine = rows.filter((r) => r.project === path.basename(project)).sort((a, b) => (b.updated > a.updated ? 1 : -1));
  const projects = new Map();
  for (const r of rows) projects.set(r.project, (projects.get(r.project) || 0) + (Number(r.cost_usd) || 0));
  const tokens = (list) => sum(list, 'input') + sum(list, 'output') + sum(list, 'cache_read') + sum(list, 'cache_write');
  const last = mine.slice(0, 5).map((r) =>
    `  ${(r.started || r.updated).slice(0, 16).replace('T', ' ')}  ${money(Number(r.cost_usd) || 0).padStart(8)}  ${kTokens(Number(r.input) + Number(r.output) + Number(r.cache_read) + Number(r.cache_write)).padStart(6)} tok  ${String(r.turns).padStart(3)} turns  ${r.model}${r.name ? '  ' + r.name : ''}`);
  return [
    'PONYTAIL SAFE DASHBOARD. Show the block below to the user exactly as it is, in a code block, then stop. Change nothing.',
    '',
    `Ponytail Safe · level ${cfg.level} · mode ${lib.readMode(project) || 'off'} · default ${cfg.defaultMode}`,
    '',
    'Features:',
    featureTable(cfg),
    '',
    `This project (${path.basename(project)}): ${mine.length} sessions, ${money(sum(mine, 'cost_usd'))}, ${kTokens(tokens(mine))} tokens, ${sum(mine, 'turns')} turns`,
    ...(last.length ? ['Last sessions:', ...last] : []),
    `All projects: ${projects.size} projects, ${rows.length} sessions, ${money(sum(rows, 'cost_usd'))}`,
    ...[...projects].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([p, c]) => `  ${p.padEnd(30)} ${money(c)}`),
    '',
    `Local files: ${lib.dataDir()} (ledger.csv, audit.jsonl, config.json). Nothing leaves this machine.`,
  ].join('\n');
}

// What the sandbox let this hook do, so a broken install can be diagnosed without guessing.
function doctor(cfg) {
  const os = require('os');
  const perm = process.permission;
  const can = (scope, p) => (perm ? (perm.has(scope, p) ? 'yes' : 'NO') : 'no sandbox');
  const data = lib.dataDir();
  let saved = 'no config.json yet';
  try { saved = fs.statSync(lib.configPath()).isFile() ? 'config.json present' : saved; } catch (e) { /* none */ }
  return [
    'PONYTAIL SAFE DOCTOR. Show the block below to the user exactly as it is, in a code block, then stop. Change nothing.',
    '',
    `node ${process.version} on ${process.platform} · sandbox ${perm ? 'on' : 'OFF'} · level ${cfg.level}`,
    `HOME=${process.env.HOME || '(not set)'} · home folder ${os.homedir()}`,
    `data folder   ${data}  (${saved})`,
    `  may read    ${can('fs.read', data)}`,
    `  may write   ${can('fs.write', data)}`,
    `plugin        ${lib.pluginRoot()}  may read ${can('fs.read', lib.pluginRoot())}`,
    `transcripts   ${lib.projectsDir()}  may read ${can('fs.read', lib.projectsDir())}`,
    `flags         ${process.execArgv.filter((a) => a.startsWith('--')).join(' ') || '(none)'}`,
  ].join('\n');
}

function help() {
  return 'PONYTAIL SAFE COMMANDS. Show this list to the user:\n' +
    '  /ponytail [lite|full|ultra|off]   coding mode for this session\n' +
    '  /ponytail status                  dashboard: level, features, cost and tokens\n' +
    '  /ponytail doctor                  what the sandbox lets the hooks do (for a broken install)\n' +
    '  /ponytail level safe|controlled|developer\n' +
    '  /ponytail allow <feature> | /ponytail deny <feature>\n' +
    '  /ponytail default lite|full|ultra|off\n' +
    '  /ponytail import | /ponytail import apply   (developer level + allow import)\n' +
    '  "stop ponytail" or "normal mode"  ponytail off';
}

// Past sessions of all projects into the ledger. Dry run without `apply`: counts files, reads none.
function runImport(cfg, apply) {
  if (!lib.enabled(cfg, 'import')) {
    return 'PONYTAIL SAFE: import is off. It needs `/ponytail level developer` and then `/ponytail allow import`. Tell the user this in one line.';
  }
  const root = lib.projectsDir();
  let dirs = [];
  try { dirs = fs.readdirSync(root, { withFileTypes: true }).filter((d) => d.isDirectory() && !d.name.startsWith('.')); } catch (e) { /* none */ }
  const files = [];
  for (const d of dirs) {
    try {
      for (const f of fs.readdirSync(path.join(root, d.name))) if (/^[\w-]+\.jsonl$/.test(f)) files.push({ project: d.name, file: path.join(root, d.name, f) });
    } catch (e) { /* unreadable folder */ }
  }
  if (!apply) {
    lib.audit(cfg, 'UserPromptSubmit', 'import-dry-run', { transcripts: files.length, folders: dirs.length }, true);
    return `PONYTAIL SAFE IMPORT (dry run, nothing read): ${files.length} transcripts in ${dirs.length} project folders under ${root}. ` +
      '`/ponytail import apply` would read them and keep only usage numbers' + (lib.enabled(cfg, 'names') ? ' and the first prompt line as name' : '') +
      '. Tell the user this in two lines.';
  }
  const start = Date.now();
  const have = new Set(lib.readLedger().map((r) => r.session));
  const rows = [];
  let read = 0;
  let stopped = false;
  for (const { project, file } of files) {
    if (Date.now() - start > IMPORT_MS) { stopped = true; break; }
    const session = path.basename(file, '.jsonl').replace(/[^\w-]/g, '').slice(0, 64);
    if (have.has(session)) continue;
    const real = lib.safeTranscript(file);
    if (!real) continue;
    let s;
    try { s = lib.sessionStats([real, ...lib.subagentFiles(real)], lib.enabled(cfg, 'names')); read++; } catch (e) { continue; }
    if (!s.model || !s.turns) continue;
    rows.push({ session, started: s.started || '', updated: s.started || '', project: s.cwd ? path.basename(s.cwd) : project,
      level: 'import', mode: '', model: s.model, turns: s.turns, input: s.input, output: s.output, cache_read: s.cacheRead,
      cache_write: s.cacheWrite, cost_usd: s.cost === null ? '' : s.cost.toFixed(4), name: s.name });
  }
  if (rows.length) lib.upsertLedger(rows);
  lib.audit(cfg, 'UserPromptSubmit', 'import-apply', { transcriptsRead: read, rowsAdded: rows.length, stoppedEarly: stopped }, true);
  return `PONYTAIL SAFE IMPORT: read ${read} transcripts, added ${rows.length} sessions to the ledger` +
    (stopped ? ' (stopped after 20 s; run `/ponytail import apply` again to continue)' : '') + '. Tell the user this in one line.';
}

function handle(cfg, project, args) {
  const [cmd = '', arg = ''] = args.toLowerCase().split(/\s+/).filter(Boolean);
  const say = (t) => 'PONYTAIL SAFE: ' + t + ' Tell the user this in one or two short lines.';

  if (cmd === '' || lib.MODES.includes(cmd)) {
    const mode = cmd || (lib.readMode(project) && lib.readMode(project) !== 'off' ? lib.readMode(project) : (cfg.defaultMode === 'off' ? 'full' : cfg.defaultMode));
    if (mode === 'off') { lib.clearMode(project); return 'PONYTAIL MODE OFF'; }
    lib.setMode(project, mode, cfg);
    lib.audit(cfg, 'UserPromptSubmit', 'mode', { mode });
    return 'PONYTAIL MODE CHANGED — level: ' + mode + '\n\n' + lib.instructions(mode, cfg);
  }
  if (cmd === 'status' || cmd === 'dashboard') return dashboard(cfg, project);
  if (cmd === 'help') return help();
  if (cmd === 'doctor') return doctor(cfg);
  if (cmd === 'default') {
    if (!lib.MODES.includes(arg)) return say('unknown mode "' + arg + '". Use lite, full, ultra or off.');
    cfg.defaultMode = arg;
    lib.saveConfig(cfg);
    lib.audit(cfg, 'UserPromptSubmit', 'default-mode', { mode: arg }, true);
    return say('new sessions start in ' + arg + '.');
  }
  if (cmd === 'level') {
    if (!lib.LEVELS.includes(arg)) return say('unknown level "' + arg + '". Use safe, controlled or developer.');
    const from = cfg.level;
    cfg.level = arg;
    lib.saveConfig(cfg);
    lib.audit(cfg, 'UserPromptSubmit', 'level', { from, to: arg }, true);
    const warn = arg === 'developer'
      ? ' WARNING: developer level allows features that read more of your data (past sessions of all projects, prompt text as task names). Each one stays off until you allow it by name, and every allow is logged.'
      : '';
    return say(`level changed from ${from} to ${arg}.${warn} Features now:\n${featureTable(cfg)}`);
  }
  if (cmd === 'allow' || cmd === 'deny') {
    const f = lib.FEATURES[arg];
    if (!f) return say('unknown feature "' + arg + '". Features: ' + Object.keys(lib.FEATURES).join(', ') + '.');
    if (cmd === 'allow') {
      if (!lib.levelAllows(cfg.level, arg)) return say(`${arg} needs level ${f.level} first (\`/ponytail level ${f.level}\`). Nothing changed.`);
      if (f.consent) cfg.consent[arg] = new Date().toISOString();
      cfg.denied = cfg.denied.filter((x) => x !== arg);
    } else {
      delete cfg.consent[arg];
      if (!cfg.denied.includes(arg)) cfg.denied.push(arg);
    }
    lib.saveConfig(cfg);
    lib.audit(cfg, 'UserPromptSubmit', cmd, { feature: arg }, true);
    return say(cmd === 'allow'
      ? `${arg} is now ON. What it does: ${f.desc}. Undo with \`/ponytail deny ${arg}\`.`
      : `${arg} is now OFF.`);
  }
  if (cmd === 'import') return runImport(cfg, arg === 'apply');
  return null; // unknown argument: let the skill answer
}

lib.readInput((input) => {
  const prompt = String(input.prompt || '').trim();
  const cfg = lib.loadConfig();
  const project = lib.projectDir(input);
  if (STOP.test(prompt)) {
    lib.clearMode(project);
    lib.audit(cfg, 'UserPromptSubmit', 'mode', { mode: 'off' });
    return lib.output('UserPromptSubmit', 'PONYTAIL MODE OFF');
  }
  const m = prompt.match(CMD);
  if (!m || /\n/.test(prompt)) return; // one line only: a pasted block never counts as a command
  let out;
  try {
    out = handle(cfg, project, m[1] || '');
  } catch (e) {
    // Say so instead of failing silently: a command that changed nothing must not look like it worked.
    out = `PONYTAIL SAFE: the command failed (${e.code || e.name}: ${e.message}). Nothing was changed. ` +
      'Tell the user this in one line and suggest `/ponytail doctor`.';
  }
  if (out) lib.output('UserPromptSubmit', out);
});
