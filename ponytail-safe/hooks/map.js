'use strict';
// Codebase map: top-level function/class/export names per folder, so "reuse first" costs no search.
// Ponytail Safe version: a plain directory walk, no `git` subprocess. Hard limits: 1500 files,
// depth 6, 64 KB per file, 1.5 s, skips dot-folders, symlinks, vendored, generated and secret files.
// It returns names only, never file contents.

const fs = require('fs');
const path = require('path');
const os = require('os');

const BUDGET = 2000;
const MAX_FILES = 1500;
const MAX_DEPTH = 6;
const MAX_BYTES = 64 * 1024;
const MAX_MS = 1500;
const SRC = /\.(py|js|jsx|mjs|cjs|ts|tsx|go|rs|rb|java|kt|php|swift|cs)$/;
const SKIP_DIR = /^(node_modules|dist|build|out|vendor|venv|__pycache__|coverage|target|migrations|fixtures|tests?|__tests__|spec)$/;
const SKIP_FILE = /(^test_|(_test|\.test|\.spec|\.gen|\.min|\.d)\.[a-z]+$)|secret|credential|password|token|private/i;
const SHARED = /(util|helper|lib|common|shared|service|component|hook|core|model|schema|api)/i;

const PATTERNS = {
  py: [/^(?:async\s+)?def\s+([A-Za-z]\w*)/gm, /^class\s+([A-Za-z]\w*)/gm],
  js: [/^export\s+(?:default\s+)?(?:async\s+)?(?:function\*?|class|const|let|var|interface|type|enum)\s+([A-Za-z_$][\w$]*)/gm],
  go: [/^func\s+(?:\([^)]*\)\s*)?([A-Z]\w*)/gm, /^type\s+([A-Z]\w*)/gm],
  rs: [/^pub\s+(?:async\s+)?(?:fn|struct|enum|trait|type)\s+(\w+)/gm],
  rb: [/^\s*(?:def|class|module)\s+([A-Za-z][\w.]*)/gm],
  jvm: [/^\s*(?:public\s+)?(?:static\s+)?(?:final\s+)?(?:class|interface|enum|record)\s+(\w+)/gm],
};
const LANG = { py: 'py', js: 'js', jsx: 'js', mjs: 'js', cjs: 'js', ts: 'js', tsx: 'js', go: 'go', rs: 'rs',
  rb: 'rb', java: 'jvm', kt: 'jvm', swift: 'jvm', cs: 'jvm', php: 'jvm' };

// The project root must be a real folder, and never the home folder or a filesystem root.
function okRoot(root) {
  try {
    const real = fs.realpathSync(root);
    // No realpath of the home folder: the hook may not read it, which is the point.
    if (real === path.parse(real).root || real === path.resolve(process.env.HOME || os.homedir())) return null;
    return fs.statSync(real).isDirectory() ? real : null;
  } catch (e) {
    return null;
  }
}

function buildMap(root) {
  const start = Date.now();
  const real = okRoot(root);
  if (!real) return { text: '', files: 0 };
  const files = [];
  (function walk(dir, depth) {
    if (depth > MAX_DEPTH || files.length >= MAX_FILES || Date.now() - start > MAX_MS) return;
    let ents = [];
    try { ents = fs.readdirSync(dir, { withFileTypes: true }); } catch (e) { return; }
    for (const ent of ents) {
      if (ent.name.startsWith('.') || ent.isSymbolicLink()) continue;
      const full = path.join(dir, ent.name);
      if (ent.isDirectory()) { if (!SKIP_DIR.test(ent.name)) walk(full, depth + 1); }
      else if (ent.isFile() && SRC.test(ent.name) && !SKIP_FILE.test(ent.name) && files.length < MAX_FILES) files.push(full);
    }
  })(real, 0);

  files.sort((a, b) => (SHARED.test(b) - SHARED.test(a)) || a.localeCompare(b));
  const dirs = new Map();
  let read = 0;
  for (const file of files) {
    if (Date.now() - start > MAX_MS) break;
    let text;
    try {
      const fd = fs.openSync(file, 'r');
      const buf = Buffer.alloc(MAX_BYTES);
      text = buf.toString('utf8', 0, fs.readSync(fd, buf, 0, MAX_BYTES, 0));
      fs.closeSync(fd);
      read++;
    } catch (e) { continue; }
    const names = [];
    for (const re of PATTERNS[LANG[path.extname(file).slice(1)]] || []) {
      for (const m of text.matchAll(re)) if (!m[1].startsWith('_') && !names.includes(m[1])) names.push(m[1]);
    }
    if (!names.length) continue;
    const rel = path.relative(real, path.dirname(file)).replace(/\\/g, '/') || '.';
    dirs.set(rel, [...(dirs.get(rel) || []), names]);
  }

  const lines = [];
  let used = 0;
  let skipped = 0;
  for (const [dir, perFile] of dirs) {
    const names = [...new Set(perFile.flatMap((n) => n.slice(0, perFile.length > 8 ? 1 : 3)))];
    const line = `${dir}/: ${names.slice(0, 30).join(', ')}${names.length > 30 ? ', ...' : ''}`;
    if (used + line.length > BUDGET) { skipped++; continue; }
    lines.push(line);
    used += line.length + 1;
  }
  if (!lines.length) return { text: '', files: read };
  return {
    text: 'Codebase map (what already exists; reuse it, read a file only when you need its details):\n' +
      lines.join('\n') + (skipped ? `\n(${skipped} more folders not listed)` : ''),
    files: read,
  };
}

module.exports = { buildMap };
