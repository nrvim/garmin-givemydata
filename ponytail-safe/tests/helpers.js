'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const ROOT = path.join(__dirname, '..');
const HOOKS = JSON.parse(fs.readFileSync(path.join(ROOT, 'hooks', 'hooks.json'), 'utf8')).hooks;

// A fresh fake machine: HOME with ~/.config and ~/.claude/projects, and a project folder.
function sandbox() {
  const base = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'pts-')));
  const home = path.join(base, 'home');
  const project = path.join(base, 'work', 'demo-app');
  fs.mkdirSync(path.join(home, '.config'), { recursive: true });
  fs.mkdirSync(path.join(home, '.claude', 'projects', '-work-demo-app'), { recursive: true });
  fs.mkdirSync(path.join(project, 'src'), { recursive: true });
  fs.writeFileSync(path.join(project, 'src', 'util.js'), 'export function slugify(s) { return s }\nexport const MAX = 3\n');
  fs.writeFileSync(path.join(project, 'app.py'), 'def main():\n    pass\nclass Server:\n    pass\n');
  fs.writeFileSync(path.join(base, 'outside-secret.txt'), 'TOP-SECRET-OUTSIDE');
  const data = path.join(home, '.config', 'ponytail-safe');
  return { base, home, project, data, transcripts: path.join(home, '.claude', 'projects', '-work-demo-app') };
}

const commandFor = (event) => HOOKS[event][0].hooks[0].command;

const envFor = (sb) => ({ PATH: process.env.PATH, HOME: sb.home, CLAUDE_PLUGIN_ROOT: ROOT, CLAUDE_PROJECT_DIR: sb.project });

// The sandbox flags the launcher would use for every hook, worked out in the sandbox's environment.
function flagsIn(sb) {
  const code = `const l=require(${JSON.stringify(path.join(ROOT, 'hooks', 'launch.js'))});` +
    'console.log(JSON.stringify(Object.fromEntries(Object.keys(l.HOOKS).map((n)=>[n,l.flagsFor(n)]))))';
  const r = spawnSync(process.execPath, ['-e', code], { env: envFor(sb), cwd: sb.project, encoding: 'utf8' });
  return JSON.parse(r.stdout);
}

// Runs the production hook command (permission flags included) through bash, with the tripwire preloaded.
function runHook(sb, event, input, { tripwire = true, raw } = {}) {
  const env = { ...envFor(sb), NODE_OPTIONS: tripwire ? `--require ${path.join(__dirname, 'tripwire.js')}` : '' };
  const stdin = raw !== undefined ? raw : JSON.stringify({ cwd: sb.project, session_id: 'sess-1', ...input });
  const r = spawnSync('bash', ['-c', commandFor(event)], { input: stdin, env, cwd: sb.project, encoding: 'utf8', timeout: 30000 });
  let json = null;
  try { json = r.stdout ? JSON.parse(r.stdout) : null; } catch (e) { json = null; }
  const context = json && json.hookSpecificOutput ? json.hookSpecificOutput.additionalContext || '' : '';
  return { ...r, json, context };
}

const prompt = (sb, text) => runHook(sb, 'UserPromptSubmit', { prompt: text, hook_event_name: 'UserPromptSubmit' });

// Every file under a folder with its content, to diff before and after a hook.
function tree(dir) {
  const out = {};
  (function walk(d) {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p); else out[p] = e.isSymbolicLink() ? 'link' : fs.readFileSync(p, 'utf8');
    }
  })(dir);
  return out;
}

function changed(before, after) {
  return Object.keys({ ...before, ...after }).filter((k) => before[k] !== after[k]);
}

// A Claude Code-like transcript: one typed prompt, one assistant reply with usage.
function writeTranscript(sb, id, { prompt: text = 'my secret plan: password hunter2', model = 'claude-opus-5-5' } = {}) {
  const file = path.join(sb.transcripts, id + '.jsonl');
  const lines = [
    { type: 'user', cwd: sb.project, sessionId: id, timestamp: '2026-11-06T10:00:00.000Z', message: { role: 'user', content: text } },
    { type: 'assistant', timestamp: '2026-11-06T10:00:05.000Z', message: { id: 'msg_1', model, usage: { input_tokens: 1000, output_tokens: 500, cache_read_input_tokens: 2000, cache_creation_input_tokens: 0 }, content: [{ type: 'text', text: 'reply with SECRET-REPLY' }] } },
    { type: 'assistant', timestamp: '2026-11-06T10:00:06.000Z', message: { id: 'msg_1', model, usage: { input_tokens: 1000, output_tokens: 500, cache_read_input_tokens: 2000, cache_creation_input_tokens: 0 } } },
  ];
  fs.writeFileSync(file, lines.map((l) => JSON.stringify(l)).join('\n') + '\n');
  return file;
}

module.exports = { ROOT, HOOKS, sandbox, runHook, prompt, tree, changed, writeTranscript, commandFor, flagsIn };
