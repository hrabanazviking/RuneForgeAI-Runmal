/* Rúnmál mobile drawer (S310).
 *
 * The chat sidebar becomes an off-canvas drawer on narrow viewports.
 * The pure state core (open/closed transitions) is unit-tested under
 * Node; the browser glue binds the toggle button, scrim, Escape key,
 * and chat selection (selecting a chat closes the drawer).
 */
"use strict";

/* -- Pure core (unit-tested under Node) ---------------------------------- */

function createDrawer() {
  return { open: false };
}

function toggleDrawer(state) {
  return { open: !state.open };
}

function openDrawer(state) {
  return { open: true };
}

function closeDrawer(state) {
  return { open: false };
}

var drawerCore = {
  createDrawer: createDrawer,
  toggleDrawer: toggleDrawer,
  openDrawer: openDrawer,
  closeDrawer: closeDrawer,
};

if (typeof module !== "undefined" && module.exports) {
  module.exports = drawerCore;
}

/* -- Browser glue ---------------------------------------------------------- */

if (typeof window !== "undefined" && typeof document !== "undefined") {
  var state = createDrawer();

  function apply() {
    var sidebar = document.getElementById("sidebar");
    var scrim = document.getElementById("scrim");
    var btn = document.getElementById("sidebar-toggle");
    if (sidebar) sidebar.classList.toggle("open", state.open);
    if (scrim) scrim.classList.toggle("hidden", !state.open);
    if (btn) btn.setAttribute("aria-expanded", state.open ? "true" : "false");
  }

  window.RunmalDrawer = {
    toggle: function () { state = toggleDrawer(state); apply(); },
    open: function () { state = openDrawer(state); apply(); },
    close: function () { state = closeDrawer(state); apply(); },
    isOpen: function () { return state.open; },
  };

  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("sidebar-toggle");
    if (btn) btn.addEventListener("click", window.RunmalDrawer.toggle);
    var scrim = document.getElementById("scrim");
    if (scrim) scrim.addEventListener("click", window.RunmalDrawer.close);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && state.open) window.RunmalDrawer.close();
    });
    apply();
  });
}
