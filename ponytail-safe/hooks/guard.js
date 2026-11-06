'use strict';
// PreToolUse: stops the agent from changing Ponytail Safe's own config, consent or ledger,
// so only the user (typing /ponytail ...) can grant a permission. Inspects the tool input
// in memory only; this hook may read nothing but the plugin itself.
// shortcut: path and text matching, so a symlink made earlier or an obfuscated shell command can get past it.
// It is a second line of defence; the first is that consent only comes from a typed prompt.
const path = require('path');
const lib = require('./lib');

const deny = (reason) => process.stdout.write(JSON.stringify({
  hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'deny', permissionDecisionReason: reason },
}));

lib.readInput((input) => {
  const dir = lib.dataDir();
  const t = input.tool_input || {};
  const file = t.file_path || t.notebook_path || t.path;
  const reason = 'Ponytail Safe: its config, consent and logs in ' + dir + ' can only be changed by the user typing /ponytail commands.';
  if (typeof file === 'string' && file) {
    const abs = path.resolve(lib.projectDir(input), file);
    if (abs === dir || abs.startsWith(dir + path.sep)) return deny(reason);
  }
  if (input.tool_name === 'Bash' && typeof t.command === 'string' && /ponytail-safe/i.test(t.command) &&
      /config\.json|ledger\.csv|audit\.jsonl|modes\/|\bactive\b/i.test(t.command) &&
      !/^\s*(cat|less|head|tail|wc|ls)\s[^;&|>`$]*$/.test(t.command)) {
    return deny(reason + ' Reading them with cat, head, tail, less, wc or ls is fine.');
  }
});
