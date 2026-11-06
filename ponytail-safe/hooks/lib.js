'use strict';
// Ponytail Safe: shared core. Node stdlib only (fs, path, os, crypto, string_decoder).
// No network, no child processes, no code generation: tests/static.test.js enforces it,
// and every hook runs under `node --permission` with only the folders it needs (hooks/hooks.json).

const fs = require('fs');
const path = require('path');
const os = require('os');
const crypto = require('crypto');
const { StringDecoder } = require('string_decoder');

const LEVELS = ['safe', 'controlled', 'developer'];
const MODES = ['off', 'lite', 'full', 'ultra'];

// Each feature: the lowest level that allows it, and whether the user must also allow it by name.
const FEATURES = {
  ledger: { level: 'safe', consent: false, desc: 'records cost, tokens and turns of the current session (numbers only) in a local CSV' },
  subagents: { level: 'safe', consent: false, desc: 'gives subagents the same ruleset (text only, reads and writes nothing)' },
  audit: { level: 'controlled', consent: false, desc: 'writes a local audit log of every hook action' },
  map: { level: 'controlled', consent: true, desc: 'at session start, reads source files of this project (up to 1500 files, 64 KB each) to list function and class names' },
  names: { level: 'developer', consent: true, desc: 'stores the first line of your first prompt as the task name in the ledger' },
  import: { level: 'developer', consent: true, desc: 'lets `/ponytail import apply` read the transcripts of ALL past Claude Code sessions in all projects (usage numbers kept, text discarded)' },
};

const home = () => process.env.HOME || os.homedir();
const dataDir = () => path.join(process.env.XDG_CONFIG_HOME || path.join(home(), '.config'), 'ponytail-safe');
const claudeDir = () => process.env.CLAUDE_CONFIG_DIR || path.join(home(), '.claude');
const projectsDir = () => path.join(claudeDir(), 'projects');
const pluginRoot = () => path.join(__dirname, '..');

// ---------- files ----------

function writePrivate(file, text) {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const tmp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, text, { mode: 0o600, flag: 'wx' });
  fs.renameSync(tmp, file); // rename replaces a symlink instead of writing through it
}

function readText(file) {
  try { return fs.readFileSync(file, 'utf8').replace(/^﻿/, ''); } catch (e) { return null; }
}

// ---------- config ----------

const configPath = () => path.join(dataDir(), 'config.json');

// Anything missing, unknown or corrupt falls back to the safest value.
function loadConfig() {
  let raw = {};
  try { raw = JSON.parse(readText(configPath()) || '{}'); } catch (e) { raw = {}; }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) raw = {};
  const consent = {};
  if (raw.consent && typeof raw.consent === 'object') {
    for (const [k, v] of Object.entries(raw.consent)) if (FEATURES[k] && FEATURES[k].consent && typeof v === 'string') consent[k] = v;
  }
  return {
    level: LEVELS.includes(raw.level) ? raw.level : 'safe',
    defaultMode: MODES.includes(raw.defaultMode) ? raw.defaultMode : 'full',
    consent,
    denied: Array.isArray(raw.denied) ? raw.denied.filter((f) => FEATURES[f]) : [],
  };
}

function saveConfig(cfg) {
  writePrivate(configPath(), JSON.stringify(cfg, null, 2) + '\n');
}

const levelAllows = (level, feature) => LEVELS.indexOf(level) >= LEVELS.indexOf(FEATURES[feature].level);

function enabled(cfg, feature) {
  const f = FEATURES[feature];
  if (!f || !levelAllows(cfg.level, feature)) return false;
  return f.consent ? Boolean(cfg.consent[feature]) : !cfg.denied.includes(feature);
}

// ---------- audit log ----------

const auditPath = () => path.join(dataDir(), 'audit.jsonl');

// Local only. Never logs prompt text or file contents: event names, counts and paths.
function audit(cfg, hook, action, details = {}, always = false) {
  if (!always && !enabled(cfg, 'audit')) return;
  try {
    const file = auditPath();
    try { if (fs.statSync(file).size > 1024 * 1024) fs.renameSync(file, file + '.1'); } catch (e) { /* none yet */ }
    fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
    fs.appendFileSync(file, JSON.stringify({ ts: new Date().toISOString(), level: cfg.level, hook, action, ...details }) + '\n', { mode: 0o600 });
  } catch (e) { /* audit is best-effort, never blocks the session */ }
}

// ---------- mode (lite/full/ultra/off) per project ----------

function projectDir(input) {
  return path.resolve(process.env.CLAUDE_PROJECT_DIR || (input && typeof input.cwd === 'string' && input.cwd) || process.cwd());
}
const modeFile = (project) => path.join(dataDir(), 'modes', crypto.createHash('sha256').update(project).digest('hex'));

function readMode(project) {
  const m = (readText(modeFile(project)) || '').trim();
  return MODES.includes(m) ? m : null;
}

function setMode(project, mode, cfg) {
  writePrivate(modeFile(project), mode);
  writePrivate(path.join(dataDir(), 'active'), `${cfg.level}:${mode}`); // for the optional statusline
}

function clearMode(project) {
  for (const f of [modeFile(project), path.join(dataDir(), 'active')]) try { fs.unlinkSync(f); } catch (e) { /* absent */ }
}

// ---------- ruleset ----------

function instructions(mode, cfg) {
  let body = readText(path.join(pluginRoot(), 'skills', 'ponytail', 'SKILL.md')) || '';
  body = body.replace(/^---[\s\S]*?---\s*/, '')
    .split(/\r?\n/)
    .filter((line) => {
      const row = line.match(/^\|\s*\*\*(.+?)\*\*\s*\|/);
      return !(row && MODES.includes(row[1].trim()) && row[1].trim() !== mode);
    })
    .join('\n');
  return `PONYTAIL MODE ACTIVE — level: ${mode} (Ponytail Safe, safety level: ${cfg.level})\n\n${body}\n\n` +
    'Ponytail Safe rule: never create, edit or delete files in ' + dataDir() + ' and never change its consent or level yourself. ' +
    'Only the user can, by typing `/ponytail level ...` or `/ponytail allow ...`.';
}

// ---------- hook I/O ----------

function output(event, context) {
  if (!context) return;
  fs.writeSync(1, JSON.stringify({ hookSpecificOutput: { hookEventName: event, additionalContext: context } }));
}

// Reads the hook payload; never hangs a session (1 s fallback) and never fails on bad input.
function readInput(fn) {
  let data = '';
  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    let input = {};
    try { input = JSON.parse(data.replace(/^﻿/, '')) || {}; } catch (e) { input = {}; }
    try { fn(input); } catch (e) { /* fail closed: no output */ }
    process.exit(0);
  };
  process.stdin.on('data', (c) => { data += c; if (data.length > 4 * 1024 * 1024) finish(); });
  process.stdin.on('end', finish);
  process.stdin.on('error', finish);
  setTimeout(finish, 1000);
}

// ---------- transcripts ----------

const MAX_TRANSCRIPT = 512 * 1024 * 1024;

// Only a regular .jsonl file whose real path lies inside Claude Code's projects folder.
function safeTranscript(p) {
  if (typeof p !== 'string' || !p.endsWith('.jsonl')) return null;
  try {
    const root = fs.realpathSync(projectsDir());
    const real = fs.realpathSync(p);
    if (!real.startsWith(root + path.sep)) return null;
    const st = fs.statSync(real);
    return st.isFile() && st.size <= MAX_TRANSCRIPT ? real : null;
  } catch (e) {
    return null;
  }
}

function eachRecord(file, fn) {
  const fd = fs.openSync(file, 'r');
  const buf = Buffer.alloc(1 << 20);
  const dec = new StringDecoder('utf8');
  let rest = '';
  const take = (l) => { if (l.startsWith('{')) try { fn(JSON.parse(l)); } catch (e) { /* skip line */ } };
  try {
    for (let n; (n = fs.readSync(fd, buf, 0, buf.length, null)) > 0;) {
      const parts = (rest + dec.write(buf.subarray(0, n))).split('\n');
      rest = parts.pop();
      parts.forEach(take);
    }
    take(rest + dec.end());
  } finally {
    fs.closeSync(fd);
  }
}

// USD per million tokens [input, 5-min cache write, 1-h cache write, cache read, output],
// taken from Ponytail 5.3.3 (checked by its author 2026-10-17). Unknown model: no estimate.
const OPUS = [5, 6.25, 10, 0.5, 25];
const PRICES = {
  'claude-fable-5-1': [10, 12.5, 20, 0.25, 50],
  'claude-fable-5': [10, 12.5, 20, 1, 50],
  'claude-opus-5-5': [4, 5, 8, 0.2, 20],
  'claude-opus-5': OPUS, 'claude-opus-4-8': OPUS, 'claude-opus-4-7': OPUS, 'claude-opus-4-6': OPUS, 'claude-opus-4-5': OPUS,
  'claude-sonnet-5-5': [2, 2.5, 4, 0.1, 10],
  'claude-sonnet-5': [2, 2.5, 4, 0.2, 10],
  'claude-sonnet-4-6': [3, 3.75, 6, 0.3, 15],
  'claude-sonnet-4-5': [3, 3.75, 6, 0.3, 15],
  'claude-haiku-5-5': [0.1, 0.125, 0.2, 0.01, 0.5],
  'claude-haiku-4-5': [1, 1.25, 2, 0.1, 5],
};
const modelId = (m) => String(m).replace(/\[.*\]$/, '').replace(/-\d{8}$/, '');

function replyCost(model, u) {
  const p = PRICES[modelId(model)];
  if (!p || u.speed === 'fast') return null;
  const cc = u.cache_creation || {};
  const split = cc.ephemeral_5m_input_tokens !== undefined || cc.ephemeral_1h_input_tokens !== undefined;
  const w5 = split ? cc.ephemeral_5m_input_tokens || 0 : u.cache_creation_input_tokens || 0;
  const w1 = split ? cc.ephemeral_1h_input_tokens || 0 : 0;
  return ((u.input_tokens || 0) * p[0] + w5 * p[1] + w1 * p[2] + (u.cache_read_input_tokens || 0) * p[3] + (u.output_tokens || 0) * p[4]) / 1e6;
}

const isHumanPrompt = (r) => r.type === 'user' && !r.isMeta && (r.turnOrigin === 'human' || (r.origin && r.origin.kind === 'human') ||
  (r.message && (typeof r.message.content === 'string' || (Array.isArray(r.message.content) && !r.message.content.some((b) => b && b.type === 'tool_result')))));

// Usage numbers of one session (its own transcript plus its subagents'). Text is only looked at
// when `withName` is set, and then only the first line of the first typed prompt.
function sessionStats(files, withName) {
  const seen = new Set();
  const models = {};
  const s = { turns: 0, input: 0, output: 0, cacheRead: 0, cacheWrite: 0, cost: 0, own: 0, started: null, name: '', cwd: '' };
  let costKnown = true;
  files.forEach((file, i) => eachRecord(file, (r) => {
    if (i === 0 && !s.started && r.timestamp) s.started = r.timestamp;
    if (i === 0 && !s.cwd && typeof r.cwd === 'string') s.cwd = r.cwd;
    if (i === 0 && isHumanPrompt(r)) {
      s.turns++;
      if (withName && !s.name) {
        const c = r.message.content;
        const t = (typeof c === 'string' ? c : ((Array.isArray(c) && c.find((b) => b && b.type === 'text')) || {}).text || '').trim();
        if (t && !t.startsWith('<') && !t.startsWith('/')) s.name = t.split('\n')[0].slice(0, 60);
      }
    }
    if (i === 0 && r.type === 'cost-state' && typeof r.totalCostUSD === 'number') s.own = r.totalCostUSD;
    const m = r.message;
    if (r.type !== 'assistant' || !m || !m.model || m.model === '<synthetic>' || !m.usage || !m.id || seen.has(m.id)) return;
    seen.add(m.id);
    if (i === 0) models[m.model] = (models[m.model] || 0) + 1;
    const u = m.usage;
    s.input += u.input_tokens || 0;
    s.output += u.output_tokens || 0;
    s.cacheRead += u.cache_read_input_tokens || 0;
    s.cacheWrite += u.cache_creation_input_tokens || 0;
    const c = replyCost(m.model, u);
    if (c === null) costKnown = false; else s.cost += c;
  }));
  s.model = Object.keys(models).sort((a, b) => models[b] - models[a])[0] || '';
  // Claude Code's own total misses earlier runs of a reopened session; the estimate misses side calls. Larger wins.
  const known = [s.own, costKnown ? s.cost : 0].filter((v) => Number.isFinite(v) && v > 0);
  s.cost = known.length ? Math.max(...known) : null;
  return s;
}

// Subagent transcripts Claude Code keeps next to the session's own: <dir>/<session>/subagents/agent-*.jsonl
function subagentFiles(transcript) {
  const dir = path.join(path.dirname(transcript), path.basename(transcript, '.jsonl'), 'subagents');
  try {
    return fs.readdirSync(dir).filter((f) => /^agent-[\w-]+\.jsonl$/.test(f)).map((f) => safeTranscript(path.join(dir, f))).filter(Boolean);
  } catch (e) {
    return [];
  }
}

// ---------- ledger (CSV) ----------

const ledgerPath = () => path.join(dataDir(), 'ledger.csv');
const HEADER = ['session', 'started', 'updated', 'project', 'level', 'mode', 'model', 'turns', 'input', 'output', 'cache_read', 'cache_write', 'cost_usd', 'name'];

// Quoted where needed, and a leading = + - @ tab or CR is defused so a spreadsheet never runs it as a formula.
function csvField(v) {
  let s = v === null || v === undefined ? '' : String(v);
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let f = '';
  let q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) {
      if (ch === '"' && text[i + 1] === '"') { f += '"'; i++; } else if (ch === '"') q = false; else f += ch;
    } else if (ch === '"') q = true;
    else if (ch === ',') { row.push(f); f = ''; }
    else if (ch === '\n') { row.push(f); rows.push(row); row = []; f = ''; }
    else if (ch !== '\r') f += ch;
  }
  if (f !== '' || row.length) { row.push(f); rows.push(row); }
  return rows;
}

function readLedger() {
  const rows = parseCsv(readText(ledgerPath()) || '');
  return rows.filter((r) => r[0] && r[0] !== 'session').map((r) => Object.fromEntries(HEADER.map((h, i) => [h, r[i] || ''])));
}

function upsertLedger(entries) {
  const byKey = new Map(readLedger().map((e) => [e.session, e]));
  for (const e of entries) byKey.set(e.session, { ...(byKey.get(e.session) || {}), ...e });
  const text = [HEADER.join(','), ...[...byKey.values()].map((e) => HEADER.map((h) => csvField(e[h])).join(','))].join('\n') + '\n';
  writePrivate(ledgerPath(), text);
}

module.exports = {
  FEATURES, LEVELS, MODES, HEADER, PRICES,
  audit, auditPath, claudeDir, clearMode, configPath, csvField, dataDir, enabled, instructions, ledgerPath, levelAllows,
  loadConfig, output, parseCsv, pluginRoot, projectDir, projectsDir, readInput, readLedger, readMode, replyCost,
  safeTranscript, saveConfig, sessionStats, setMode, subagentFiles, upsertLedger,
};
