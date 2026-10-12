/* S302 renderer unit tests — run under Node by tests/test_s302_renderer.py.
 * Exercises the markdown-lite renderer (XSS safety, code blocks, links,
 * malformed input) and thread windowing. Exits non-zero on any failure. */
"use strict";
const assert = require("node:assert");
const R = require("../../src/runmal/web/static/renderer.js");

// -- XSS safety -------------------------------------------------------------
let out = R.renderMarkdownLite('<script>alert("x")</script>');
assert.ok(!out.includes("<script>"), "script tag must be escaped: " + out);
assert.ok(out.includes("&lt;script&gt;"));

out = R.renderMarkdownLite('"><img src=x onerror=alert(1)>');
assert.ok(!out.includes("<img"), "img tag must be escaped: " + out);

out = R.renderMarkdownLite("[click](javascript:alert(1))");
assert.ok(!out.includes("<a "), "javascript: URL must not become a link: " + out);

out = R.renderMarkdownLite('[x](https://example.com/" onclick="evil)');
assert.ok(!out.includes("<a "), "quote breakout must not form a link: " + out);
assert.ok(!out.includes('onclick="'), "no raw-quote attribute may appear: " + out);

// -- markdown-lite ------------------------------------------------------------
assert.strictEqual(R.renderMarkdownLite("a **bold** b"), "a <strong>bold</strong> b");
assert.strictEqual(R.renderMarkdownLite("a *soft* b"), "a <em>soft</em> b");
assert.strictEqual(
  R.renderMarkdownLite("use `x < y` here"),
  "use <code>x &lt; y</code> here"
);
assert.strictEqual(
  R.renderMarkdownLite("[ok](https://example.com)"),
  '<a href="https://example.com" rel="noopener noreferrer">ok</a>'
);
assert.strictEqual(R.renderMarkdownLite("l1\nl2"), "l1<br>l2");

// inline code protects its contents from further transforms
assert.strictEqual(
  R.renderMarkdownLite("`**not bold**`"),
  "<code>**not bold**</code>"
);

// -- code fences ----------------------------------------------------------------
out = R.renderMarkdownLite("before\n```\n<b>raw</b>\n```\nafter");
assert.ok(out.includes('<pre class="code-block">'), out);
assert.ok(out.includes("&lt;b&gt;raw&lt;/b&gt;"), out);
assert.ok(out.includes('class="copy-btn"'), out);
assert.ok(!out.includes("<b>raw</b>"), out);

// language label on the fence is dropped, body kept
out = R.renderMarkdownLite("```python\nprint(1)\n```");
assert.ok(out.includes("print(1)"), out);
assert.ok(!out.includes("python"), out);

// -- malformed input --------------------------------------------------------------
out = R.renderMarkdownLite("```\nunclosed fence <b>");
assert.ok(out.includes('<pre class="code-block">'), out);
assert.ok(!out.includes("<b>"), out);

out = R.renderMarkdownLite("a **unclosed bold");
assert.strictEqual(out, "a **unclosed bold");

assert.strictEqual(R.renderMarkdownLite(""), "");
assert.strictEqual(R.renderMarkdownLite(null), "");

// -- windowing ----------------------------------------------------------------------
const msgs = Array.from({ length: 250 }, (_, i) => ({ role: "user", content: "m" + i }));
let w = R.windowMessages(msgs, 100);
assert.strictEqual(w.hidden, 150);
assert.strictEqual(w.visible.length, 100);
assert.strictEqual(w.visible[0].content, "m150");
w = R.windowMessages(msgs.slice(0, 5), 100);
assert.strictEqual(w.hidden, 0);
assert.strictEqual(w.visible.length, 5);

console.log("renderer tests: ALL PASS");
