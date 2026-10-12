/* S308 palette unit tests — run under Node by tests/test_s308_palette.py.
 * Registry integrity (reachability, unique ids, no shortcut conflicts,
 * stable ids) and fuzzy ranking. Exits non-zero on any failure. */
"use strict";
const assert = require("node:assert");
const P = require("../../src/runmal/web/static/palette.js");

// the shipped registry is valid: reachable, unique, conflict-free
assert.deepStrictEqual(P.validateRegistry(P.ACTIONS), []);

// ids are stable (snapshot — changing one is a deliberate act)
assert.deepStrictEqual(
  P.ACTIONS.map((a) => a.id),
  ["nav.chat", "nav.gallery", "nav.lorebooks", "nav.editor",
   "nav.connections", "nav.tools", "nav.group", "app.theme", "chat.new"]
);

// every action is reachable: a nav target or a named run handler
for (const a of P.ACTIONS) {
  assert.ok(a.href || a.run, "unreachable action " + a.id);
  assert.ok(a.title.length > 0, "untitled action " + a.id);
}

// validator catches the failure modes it promises to catch
let bad = P.validateRegistry([
  { id: "x", title: "X", href: "/x", shortcut: "alt+1" },
  { id: "x", title: "Y", href: "/y", shortcut: "alt+1" },
  { id: "z", title: "Z" },
]);
assert.ok(bad.some((e) => e.includes("duplicate action id")), bad);
assert.ok(bad.some((e) => e.includes("shortcut conflict")), bad);
assert.ok(bad.some((e) => e.includes("not reachable")), bad);

// fuzzy ranking: intent finds its action
let top = P.filterActions(P.ACTIONS, "grp")[0];
assert.strictEqual(top.id, "nav.group");
top = P.filterActions(P.ACTIONS, "theme")[0];
assert.strictEqual(top.id, "app.theme");
top = P.filterActions(P.ACTIONS, "lore")[0];
assert.strictEqual(top.id, "nav.lorebooks");
top = P.filterActions(P.ACTIONS, "new")[0];
assert.strictEqual(top.id, "chat.new");
// empty query lists everything in registry order
let all = P.filterActions(P.ACTIONS, "");
assert.strictEqual(all.length, P.ACTIONS.length);
assert.strictEqual(all[0].id, "nav.chat");
// gibberish matches nothing
assert.deepStrictEqual(P.filterActions(P.ACTIONS, "zzzzqq"), []);

console.log("palette tests: ALL PASS");
