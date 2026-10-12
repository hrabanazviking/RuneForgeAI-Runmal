/* Rúnmál command palette + keyboard map (S308).
 *
 * One fuzzy action registry spans the whole app: every surface and key
 * in-page action is registered once with a stable id, title, keywords,
 * and an optional shortcut. The registry is validated (unique ids,
 * unique shortcuts, every action reachable) by Node unit tests; the
 * browser glue below renders the palette overlay (Ctrl/Cmd+K) and the
 * global shortcut map.
 */
"use strict";

/* -- Pure core (unit-tested under Node) ---------------------------------- */

var ACTIONS = [
  { id: "nav.chat", title: "Go to Chat", keywords: "chat talk conversation",
    href: "/chat", shortcut: "alt+1" },
  { id: "nav.gallery", title: "Go to Character Gallery", keywords: "characters gallery cards",
    href: "/gallery", shortcut: "alt+2" },
  { id: "nav.lorebooks", title: "Go to Lorebooks", keywords: "lore lorebooks world info",
    href: "/lorebooks", shortcut: "alt+3" },
  { id: "nav.editor", title: "Go to Persona Editor", keywords: "persona scenario greeting editor",
    href: "/editor", shortcut: "alt+4" },
  { id: "nav.connections", title: "Go to Connections", keywords: "connections backends models health",
    href: "/connections", shortcut: "alt+5" },
  { id: "nav.tools", title: "Go to Prompt Tools", keywords: "tools compose impersonate depth variables",
    href: "/tools", shortcut: "alt+6" },
  { id: "nav.group", title: "Go to Group Chat", keywords: "group participants strategy",
    href: "/group", shortcut: "alt+7" },
  { id: "app.theme", title: "Toggle Theme", keywords: "theme dark light appearance",
    run: "toggleTheme", shortcut: "alt+t" },
  { id: "chat.new", title: "New Chat", keywords: "new chat conversation create",
    run: "newChat", shortcut: "alt+n" },
];

function validateRegistry(actions) {
  var errors = [];
  var ids = {};
  var shortcuts = {};
  for (var i = 0; i < actions.length; i++) {
    var a = actions[i];
    if (!a.id) errors.push("action without id at index " + i);
    if (ids[a.id]) errors.push("duplicate action id: " + a.id);
    ids[a.id] = true;
    if (!a.title) errors.push("action without title: " + a.id);
    if (!a.href && !a.run) errors.push("action not reachable: " + a.id);
    if (a.shortcut) {
      var key = a.shortcut.toLowerCase();
      if (shortcuts[key]) {
        errors.push(
          "shortcut conflict: " + a.shortcut + " used by " +
            shortcuts[key] + " and " + a.id
        );
      }
      shortcuts[key] = a.id;
    }
  }
  return errors;
}

/* Subsequence fuzzy score: higher is better; -1 means no match.
 * Bonuses for contiguous runs and word starts keep rankings sane. */
function fuzzyScore(query, text) {
  var q = query.toLowerCase();
  var t = text.toLowerCase();
  if (!q) return 0;
  var score = 0;
  var ti = 0;
  var firstFound = -1;
  var prevMatched = false;
  for (var qi = 0; qi < q.length; qi++) {
    var found = -1;
    for (var j = ti; j < t.length; j++) {
      if (t[j] === q[qi]) { found = j; break; }
    }
    if (found === -1) return -1;
    if (firstFound === -1) firstFound = found;
    score += 1;
    if (prevMatched && found === ti) score += 2;         // contiguous
    if (found === 0 || t[found - 1] === " ") score += 2; // word start
    prevMatched = found === ti;
    ti = found + 1;
  }
  // Span penalty: tight matches beat scattered ones ("grp" must find
  // Group, not a G...r...p scattered across a long keyword string).
  score -= 0.2 * (ti - firstFound);
  return score;
}

function actionScore(query, action) {
  var hay = action.title + " " + (action.keywords || "") + " " + action.id;
  var best = fuzzyScore(query, hay);
  if (!query) return best;
  // Whole-word bonus: if the entire query matches inside a single word
  // ("grp" inside "group"), that is strong intent and beats scattered
  // matches across a long keyword string ("g...r...prompt").
  var words = hay.toLowerCase().split(/[^a-z0-9]+/);
  for (var i = 0; i < words.length; i++) {
    if (!words[i]) continue;
    var ws = fuzzyScore(query, words[i]);
    if (ws >= 0 && ws + 3 > best) best = ws + 3;
  }
  return best;
}

function filterActions(actions, query) {
  var scored = [];
  for (var i = 0; i < actions.length; i++) {
    var s = actionScore(query, actions[i]);
    if (s >= 0) scored.push({ action: actions[i], score: s, index: i });
  }
  scored.sort(function (x, y) {
    return y.score - x.score || x.index - y.index;
  });
  return scored.map(function (r) { return r.action; });
}

var paletteCore = {
  ACTIONS: ACTIONS,
  validateRegistry: validateRegistry,
  fuzzyScore: fuzzyScore,
  filterActions: filterActions,
};

if (typeof module !== "undefined" && module.exports) {
  module.exports = paletteCore;
}

/* -- Browser glue ---------------------------------------------------------- */

if (typeof window !== "undefined" && typeof document !== "undefined") {
  window.RunmalPalette = paletteCore;

  function runAction(action) {
    if (action.run === "toggleTheme") {
      var current =
        document.documentElement.getAttribute("data-theme") ||
        (window.matchMedia("(prefers-color-scheme: light)").matches
          ? "light" : "dark");
      var next = current === "dark" ? "light" : "dark";
      localStorage.setItem("runmal-theme", next);
      document.documentElement.setAttribute("data-theme", next);
      return;
    }
    if (action.run === "newChat") {
      var btn = document.getElementById("new-chat");
      if (btn) { btn.click(); return; }
      window.location.href = "/chat";
      return;
    }
    if (action.href) window.location.href = action.href;
  }

  function openPalette() {
    var root = document.getElementById("palette");
    if (!root) return;
    root.classList.remove("hidden");
    var input = document.getElementById("palette-input");
    input.value = "";
    renderList("");
    input.focus();
  }
  function closePalette() {
    var root = document.getElementById("palette");
    if (root) root.classList.add("hidden");
  }
  function renderList(query) {
    var list = document.getElementById("palette-list");
    if (!list) return;
    list.textContent = "";
    var results = filterActions(ACTIONS, query);
    results.forEach(function (action, i) {
      var li = document.createElement("li");
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", i === 0 ? "true" : "false");
      li.textContent = action.title + (action.shortcut
        ? "  (" + action.shortcut + ")" : "");
      if (i === 0) li.classList.add("selected");
      li.addEventListener("click", function () {
        closePalette();
        runAction(action);
      });
      list.appendChild(li);
    });
    list.dataset.count = String(results.length);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var input = document.getElementById("palette-input");
    if (input) {
      input.addEventListener("input", function () { renderList(input.value); });
      input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          var results = filterActions(ACTIONS, input.value);
          if (results.length) { closePalette(); runAction(results[0]); }
        } else if (e.key === "Escape") {
          closePalette();
        }
      });
    }
    var root = document.getElementById("palette");
    if (root) {
      root.addEventListener("click", function (e) {
        if (e.target === root) closePalette();
      });
    }
    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        openPalette();
        return;
      }
      if (e.altKey) {
        var combo = "alt+" + e.key.toLowerCase();
        for (var i = 0; i < ACTIONS.length; i++) {
          if (ACTIONS[i].shortcut === combo) {
            e.preventDefault();
            runAction(ACTIONS[i]);
            return;
          }
        }
      }
      if (e.key === "Escape") closePalette();
    });
  });
}
