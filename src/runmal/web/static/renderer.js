/* Rúnmál markdown-lite renderer + thread windowing (S302).
 *
 * XSS discipline: ALL input text is HTML-escaped before any transform
 * runs; transforms operate only on escaped text and emit a fixed set of
 * tags (strong, em, code, pre, a[href^=http]). Link URLs are restricted
 * to http/https with no whitespace or quotes. Inline/fenced code content
 * is escaped and never re-processed.
 *
 * Pure functions, no DOM: unit-tested under Node; in the browser the API
 * is exposed as window.RunmalRenderer.
 */
"use strict";

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

var LINK_RE = /\[([^\]\n]+)\]\((https?:\/\/[^\s)"']+)\)/g;
var BOLD_RE = /\*\*([^*\n]+)\*\*/g;
var ITALIC_RE = /\*([^*\n]+)\*/g;
var PLACEHOLDER = "\u0001";

function renderProse(escaped) {
  // Inline code spans are stashed first so their contents stay literal.
  var codes = [];
  var text = escaped.replace(/`([^`\n]+)`/g, function (_, body) {
    codes.push(body);
    return PLACEHOLDER + (codes.length - 1) + PLACEHOLDER;
  });
  text = text.replace(LINK_RE, function (_, label, url) {
    return '<a href="' + url + '" rel="noopener noreferrer">' + label + "</a>";
  });
  text = text.replace(BOLD_RE, "<strong>$1</strong>");
  text = text.replace(ITALIC_RE, "<em>$1</em>");
  text = text.replace(/\n/g, "<br>");
  text = text.replace(/\u0001(\d+)\u0001/g, function (_, i) {
    return "<code>" + codes[Number(i)] + "</code>";
  });
  return text;
}

function renderMarkdownLite(input) {
  var text = String(input == null ? "" : input);
  var parts = text.split("```");
  var out = [];
  for (var i = 0; i < parts.length; i++) {
    if (i % 2 === 1) {
      // Fenced code: optional language word on the first line is dropped.
      var body = parts[i].replace(/^[A-Za-z0-9_+-]*\n/, "");
      out.push(
        '<pre class="code-block"><button type="button" class="copy-btn">' +
          "Copy</button><code>" +
          escapeHtml(body.replace(/\n$/, "")) +
          "</code></pre>"
      );
    } else if (parts[i]) {
      out.push(renderProse(escapeHtml(parts[i])));
    }
  }
  return out.join("");
}

/* STT confidence markings (P-107, VX-11 rendered markings).
 * Mirrors the P-105 token law: a token matches when its
 * punctuation-stripped core, lower-cased, is a low-confidence
 * word; punctuation stays OUTSIDE the span. Escape-first XSS
 * discipline is inherited from renderMarkdownLite: the mark
 * placeholders are control characters that escaping leaves
 * alone, and the span is substituted only after every
 * transform has run, so no user text can become markup. */
var STT_PUNCT = ".,!?;:'()[]{}<>" + String.fromCharCode(34) + "“”‘’«»";
var MARK_OPEN = "";
var MARK_CLOSE = "";

function splitAffixes(token) {
  var start = 0;
  while (start < token.length && STT_PUNCT.indexOf(token[start]) >= 0) start++;
  var end = token.length;
  while (end > start && STT_PUNCT.indexOf(token[end - 1]) >= 0) end--;
  return { lead: token.slice(0, start), core: token.slice(start, end),
           trail: token.slice(end) };
}

function renderMarkedTranscript(input, lowWords) {
  var text = String(input == null ? "" : input);
  var low = {};
  (lowWords || []).forEach(function (w) {
    low[String(w).toLowerCase()] = true;
  });
  if (!Object.keys(low).length) return renderMarkdownLite(text);
  var marked = text.split(" ").map(function (token) {
    var parts = splitAffixes(token);
    if (parts.core && low[parts.core.toLowerCase()]) {
      return parts.lead + MARK_OPEN + parts.core + MARK_CLOSE + parts.trail;
    }
    return token;
  }).join(" ");
  return renderMarkdownLite(marked).replace(
    /([^]*)/g,
    function (_, core) {
      return '<span class="stt-low" title="Low speech-to-text confidence">'
        + core + "</span>";
    });
}

/* Thread windowing ("virtualized" thread): render only the newest
 * `limit` messages; the UI offers earlier ones on demand. */
function windowMessages(messages, limit) {
  if (!limit || messages.length <= limit) {
    return { visible: messages.slice(), hidden: 0 };
  }
  return { visible: messages.slice(messages.length - limit),
           hidden: messages.length - limit };
}

var api = {
  escapeHtml: escapeHtml,
  renderMarkdownLite: renderMarkdownLite,
  renderMarkedTranscript: renderMarkedTranscript,
  windowMessages: windowMessages,
};

if (typeof module !== "undefined" && module.exports) {
  module.exports = api;
} else if (typeof window !== "undefined") {
  window.RunmalRenderer = api;
}
