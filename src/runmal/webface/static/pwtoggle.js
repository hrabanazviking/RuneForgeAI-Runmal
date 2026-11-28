"use strict";
/* Runmal web face - shared password show/hide toggle (W-05B).
   Volmarr's standing UI rule: EVERY password field gets a
   show/hide toggle. One shared control lives here: any input
   marked with the hook attribute data-pw-toggle is wrapped in
   a .pw-field span with a Show/Hide button beside it. The
   toggle is DISPLAY-ONLY: it flips the input type between
   password and text and never touches the value, the form, or
   what is submitted, and it never reads a stored secret back
   (W-04 keys stay write-only; the field only ever reveals what
   the user is typing in it). Dynamic fields inherit the toggle
   automatically: a MutationObserver enhances hooked inputs as
   they are added to the page (the Connections editor, the
   First-Run connect form) and keeps each button's hidden state
   in step with a hidden input. Pattern follows the Norse Saga
   Web Hall precedent (_PW_TOGGLE_SCRIPT): a delegated click
   handler plus a .pw-field wrapper. */
(function () {
  var HOOK = "data-pw-toggle";
  var READY = "data-pw-ready";

  function makeButton(input) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "btn ghost small pw-toggle";
    b.textContent = "Show";
    b.setAttribute("aria-pressed", "false");
    b.setAttribute("aria-label", "Show password");
    b.hidden = !!input.hidden;
    return b;
  }

  function enhance(input) {
    if (!input || input.nodeType !== 1) return null;
    if (!input.hasAttribute(HOOK) || input.hasAttribute(READY)) return null;
    input.setAttribute(READY, "1");
    var wrap = document.createElement("span");
    wrap.className = "pw-field";
    if (input.parentNode) input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
    wrap.appendChild(makeButton(input));
    return wrap;
  }

  function enhanceAll(root) {
    var scope = root && root.querySelectorAll ? root : document;
    if (scope !== document && scope.matches &&
        scope.matches("input[" + HOOK + "]")) enhance(scope);
    var inputs = scope.querySelectorAll("input[" + HOOK + "]");
    for (var i = 0; i < inputs.length; i++) enhance(inputs[i]);
  }

  function syncHidden(input) {
    var wrap = input.closest ? input.closest(".pw-field") : null;
    if (!wrap) return;
    var btn = wrap.querySelector(".pw-toggle");
    if (btn) btn.hidden = !!input.hidden;
  }

  function flip(btn) {
    var wrap = btn.closest ? btn.closest(".pw-field") : null;
    if (!wrap) return;
    var input = wrap.querySelector("input");
    if (!input) return;
    var show = input.type === "password";
    input.type = show ? "text" : "password";
    btn.setAttribute("aria-pressed", show ? "true" : "false");
    btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
    btn.textContent = show ? "Hide" : "Show";
  }

  document.addEventListener("click", function (ev) {
    var b = ev.target && ev.target.closest ? ev.target.closest(".pw-toggle") : null;
    if (b) flip(b);
  });

  function watch() {
    if (!window.MutationObserver || !document.body) return;
    var obs = new MutationObserver(function (records) {
      for (var i = 0; i < records.length; i++) {
        var r = records[i];
        if (r.type === "attributes") { syncHidden(r.target); continue; }
        for (var j = 0; j < r.addedNodes.length; j++) {
          if (r.addedNodes[j].nodeType === 1) enhanceAll(r.addedNodes[j]);
        }
      }
    });
    obs.observe(document.body, { childList: true, subtree: true,
      attributes: true, attributeFilter: ["hidden"] });
  }

  function init() { enhanceAll(document); watch(); }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else { init(); }

  window.RunmalPwToggle = { enhance: enhance, enhanceAll: enhanceAll,
    flip: flip, HOOK: HOOK };
})();
