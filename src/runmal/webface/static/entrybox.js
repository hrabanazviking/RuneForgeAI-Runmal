"use strict";
/* Runmal web face - shared entry-box control set (W-11).
   Volmarr's four parts for every data entry box (2026-11-27):
   (1) auto-expanding size - a textarea grows with its content
       (capped by a max-height; past the cap the PAGE scrolls,
       the box itself never becomes a cramped fixed window);
   (2) Copy / Paste companion buttons - no confirmation, they
       act on the click;
   (3) a Clear companion - the ONLY one that asks "Are you
       sure?" first; an accidental tap never eats text;
   (4) auto-saved drafts - boxes carrying a data-draft-key are
       saved to the account (server-side, W-11 roads) as the
       user types, restored on return, retired on the page's
       successful submit/send or a confirmed Clear.
   One shared control, the pwtoggle.js pattern: every element
   with the .entry-box class is enhanced, including ones
   created later (MutationObserver). Per-kind law:
   - textarea + text-like inputs (text/search/url/email/tel):
     all four parts (drafts only with a draft key).
   - password inputs: NO companions and NO drafts - a secret
     is never copied to a clipboard by a button, never saved
     as a draft, and the W-05B show/hide toggle already lives
     there. Clear-by-button would be a footgun on a secret.
   - number inputs, selects, checkboxes, file inputs: no
     companions, no auto-grow, no drafts - there is no prose
     to copy, grow, or lose; their native controls stand.
   CLIPBOARD HONESTY (the W-08 pattern): navigator.clipboard
   is secure-context-only and this face is plain HTTP, so the
   ladder is Clipboard API -> execCommand fallback -> select
   the text and SAY SO in words on the box. Paste reads the
   clipboard where the browser allows it and otherwise says
   Ctrl+V works as usual. A companion click NEVER fails
   silently: every outcome lands as a status word on the box. */
(function () {
  var READY = "data-entrybox-ready";
  var DEBOUNCE_MS = 400;
  var MAX_HEIGHT = 480;

  function kindOf(el) {
    if (!el || el.nodeType !== 1) return null;
    var tag = (el.tagName || "").toLowerCase();
    if (tag === "textarea") return "textarea";
    if (tag === "select") return "select";
    if (tag !== "input") return null;
    var t = (el.getAttribute("type") || "text").toLowerCase();
    if (t === "password") return "password";
    if (t === "checkbox" || t === "radio" || t === "file" ||
        t === "hidden" || t === "submit" || t === "button") return t;
    if (t === "number" || t === "range" || t === "date" ||
        t === "time" || t === "color") return "number";
    return "text";
  }

  function companionsFor(kind) {
    return kind === "textarea" || kind === "text";
  }

  function say(state, words) {
    if (state && state.status) state.status.textContent = words || "";
  }

  function autoGrow(el) {
    if (!el || (el.tagName || "").toLowerCase() !== "textarea") return;
    el.style.height = "auto";
    var h = el.scrollHeight || 0;
    if (h > MAX_HEIGHT) {
      el.style.height = MAX_HEIGHT + "px";
      el.style.overflowY = "auto";
    } else {
      el.style.height = h + "px";
      el.style.overflowY = "hidden";
    }
  }

  // ---- drafts -------------------------------------------------------
  function draftKey(el) {
    return el.getAttribute("data-draft-key") || null;
  }

  function apiDraft(method, key, text) {
    var opts = { method: method, headers: { "Content-Type": "application/json" } };
    if (method === "PUT" || method === "POST") {
      opts.method = "PUT";
      opts.body = JSON.stringify({ key: key, text: text });
      return fetch("/webface/draft", opts);
    }
    if (method === "DELETE") {
      opts.body = JSON.stringify({ key: key });
      return fetch("/webface/draft", opts);
    }
    return fetch("/webface/draft?key=" + encodeURIComponent(key));
  }

  function scheduleSave(el, state) {
    var key = draftKey(el);
    if (!key) return;
    if (state.timer) clearTimeout(state.timer);
    state.timer = setTimeout(function () {
      state.timer = null;
      apiDraft("PUT", key, el.value).then(function (resp) {
        if (resp && resp.ok) say(state, el.value ? "Draft saved" : "");
      }).catch(function () { /* offline: the text stays in the box */ });
    }, DEBOUNCE_MS);
  }

  function restoreDraft(el, state) {
    var key = draftKey(el);
    if (!key) return Promise.resolve(false);
    var initial = state.initial;
    return apiDraft("GET", key).then(function (resp) {
      if (!resp || !resp.ok) return false;
      return resp.json();
    }).then(function (data) {
      if (!data || typeof data.text !== "string" || data.text === "") return false;
      // Restore semantics (stated in w11.py): the draft fills the
      // box ONLY when the box is still empty / untouched - a value
      // the page itself loaded is never clobbered.
      if (el.value !== "" && el.value !== initial) return false;
      if (el.value !== "") return false;
      el.value = data.text;
      autoGrow(el);
      say(state, "Draft restored");
      return true;
    }).catch(function () { return false; });
  }

  function retireDraft(el, state) {
    var key = draftKey(el);
    if (!key) return Promise.resolve(false);
    if (state && state.timer) { clearTimeout(state.timer); state.timer = null; }
    return apiDraft("DELETE", key).then(function (resp) {
      return !!(resp && resp.ok);
    }).catch(function () { return false; });
  }

  // ---- clipboard ladder ----------------------------------------------
  function copyField(el, state) {
    function done(words) { say(state, words); return words; }
    var text = el.value;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(function () {
        return done("Copied");
      }).catch(function () { return fallback(); });
    }
    return Promise.resolve(fallback());
    function fallback() {
      var ok = false;
      try {
        el.focus(); el.select();
        ok = !!(document.execCommand && document.execCommand("copy"));
      } catch (err) { ok = false; }
      if (ok) return done("Copied");
      try { el.focus(); el.select(); } catch (err) { /* words still land */ }
      return done("Clipboard isn't available over this connection - the text is selected, Ctrl+C copies it");
    }
  }

  function pasteField(el, state) {
    function done(words) { say(state, words); return words; }
    if (navigator.clipboard && navigator.clipboard.readText) {
      return navigator.clipboard.readText().then(function (text) {
        insertText(el, text || "");
        return done("Pasted");
      }).catch(function () { return unavailable(); });
    }
    return Promise.resolve(unavailable());
    function unavailable() {
      try { el.focus(); } catch (err) { /* words still land */ }
      return done("Clipboard isn't available over this connection - Ctrl+V pastes as usual");
    }
  }

  function insertText(el, text) {
    var start = typeof el.selectionStart === "number" ? el.selectionStart : el.value.length;
    var end = typeof el.selectionEnd === "number" ? el.selectionEnd : el.value.length;
    el.value = el.value.slice(0, start) + text + el.value.slice(end);
    try { el.selectionStart = el.selectionEnd = start + text.length; } catch (err) {}
    el.dispatchEvent(new Event("input", { bubbles: true }));
    autoGrow(el);
  }

  function clearField(el, state) {
    var ask = (window.RunmalEntryBox && window.RunmalEntryBox.confirmClear) ||
      function (q) { return window.confirm(q); };
    if (!ask("Are you sure? This clears the box.")) {
      say(state, "Clear cancelled - your text is untouched");
      return Promise.resolve(false);
    }
    el.value = "";
    el.dispatchEvent(new Event("input", { bubbles: true }));
    autoGrow(el);
    return retireDraft(el, state).then(function () {
      say(state, "Cleared");
      return true;
    });
  }

  // ---- enhancement ----------------------------------------------------
  var states = new Map();

  function makeButton(cls, label, fn) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "btn ghost small " + cls;
    b.textContent = label;
    b.addEventListener("click", function () { fn(); });
    return b;
  }

  function enhance(el) {
    if (!el || el.nodeType !== 1) return null;
    if (!el.classList || !el.classList.contains("entry-box")) return null;
    if (el.hasAttribute(READY)) return states.get(el) || null;
    var kind = kindOf(el);
    if (!kind || !companionsFor(kind)) {
      // Per-kind law: selects/numbers/passwords/checkbox/file
      // get no companions; mark ready so the observer lets go.
      el.setAttribute(READY, "kind:" + (kind || "none"));
      return null;
    }
    el.setAttribute(READY, "1");
    var state = { el: el, kind: kind, initial: el.value, timer: null, status: null };
    states.set(el, state);
    var wrap = document.createElement("span");
    wrap.className = "entrybox-wrap";
    if (el.parentNode) el.parentNode.insertBefore(wrap, el);
    wrap.appendChild(el);
    var tools = document.createElement("span");
    tools.className = "entrybox-tools";
    tools.appendChild(makeButton("eb-copy", "Copy", function () { copyField(el, state); }));
    tools.appendChild(makeButton("eb-paste", "Paste", function () { pasteField(el, state); }));
    tools.appendChild(makeButton("eb-clear", "Clear", function () { clearField(el, state); }));
    var status = document.createElement("span");
    status.className = "entrybox-status muted";
    status.setAttribute("aria-live", "polite");
    state.status = status;
    tools.appendChild(status);
    wrap.appendChild(tools);
    el.addEventListener("input", function () {
      autoGrow(el);
      scheduleSave(el, state);
    });
    autoGrow(el);
    if (draftKey(el)) restoreDraft(el, state);
    return state;
  }

  function enhanceAll(root) {
    var scope = root && root.querySelectorAll ? root : document;
    if (scope !== document && scope.matches && scope.matches(".entry-box")) enhance(scope);
    var fields = scope.querySelectorAll(".entry-box");
    for (var i = 0; i < fields.length; i++) enhance(fields[i]);
  }

  function bindDraft(el, key) {
    /* Pages whose draft context arrives late (the chat composer
       is per chat) set the key here; restore runs for the new
       key and pending saves for the old key are dropped. */
    if (!el) return;
    var state = states.get(el) || enhance(el);
    el.setAttribute("data-draft-key", key);
    if (state) {
      if (state.timer) { clearTimeout(state.timer); state.timer = null; }
      state.initial = el.value;
      restoreDraft(el, state);
    }
  }

  function watch() {
    if (!window.MutationObserver || !document.body) return;
    var obs = new MutationObserver(function (records) {
      for (var i = 0; i < records.length; i++) {
        var nodes = records[i].addedNodes;
        for (var j = 0; j < nodes.length; j++) {
          if (nodes[j].nodeType === 1) enhanceAll(nodes[j]);
        }
      }
    });
    obs.observe(document.body, { childList: true, subtree: true });
  }

  function init() { enhanceAll(document); watch(); }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else { init(); }

  window.RunmalEntryBox = {
    enhance: enhance, enhanceAll: enhanceAll, bindDraft: bindDraft,
    autoGrow: autoGrow, copyField: copyField, pasteField: pasteField,
    clearField: clearField, restoreDraft: restoreDraft,
    retireDraft: function (el) {
      return retireDraft(el, states.get(el) || { timer: null });
    },
    stateOf: function (el) { return states.get(el) || null; },
    kindOf: kindOf,
    confirmClear: null, // tests may stub; default is window.confirm
    MAX_HEIGHT: MAX_HEIGHT,
  };
})();
