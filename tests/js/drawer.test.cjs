/* S310 drawer unit tests — run under Node by tests/test_s310_responsive.py.
 * The drawer state machine: closed by default, toggle flips, open/close
 * are idempotent, selecting (close) always ends closed. */
"use strict";
const assert = require("node:assert");
const D = require("../../src/runmal/web/static/drawer.js");

let s = D.createDrawer();
assert.deepStrictEqual(s, { open: false });
s = D.toggleDrawer(s);
assert.strictEqual(s.open, true);
s = D.toggleDrawer(s);
assert.strictEqual(s.open, false);
s = D.openDrawer(D.openDrawer(s));
assert.strictEqual(s.open, true);
s = D.closeDrawer(s);
assert.strictEqual(s.open, false);
s = D.closeDrawer(s);
assert.strictEqual(s.open, false);
// transitions are pure: input state is not mutated
const frozen = D.createDrawer();
D.toggleDrawer(frozen);
assert.strictEqual(frozen.open, false);

console.log("drawer tests: ALL PASS");
