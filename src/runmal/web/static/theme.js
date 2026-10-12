/* Rúnmál theme control (S301). Persists the explicit choice in local
   storage; with no choice stored, the OS preference rules via the
   prefers-color-scheme token block. Loaded on every page. */
"use strict";

(function () {
  var KEY = "runmal-theme";
  function apply(theme) {
    if (theme === "dark" || theme === "light") {
      document.documentElement.setAttribute("data-theme", theme);
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
  }
  apply(localStorage.getItem(KEY));
  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("theme-toggle");
    if (!btn) return;
    btn.addEventListener("click", function () {
      var current =
        document.documentElement.getAttribute("data-theme") ||
        (window.matchMedia("(prefers-color-scheme: light)").matches
          ? "light"
          : "dark");
      var next = current === "dark" ? "light" : "dark";
      localStorage.setItem(KEY, next);
      apply(next);
    });
  });
})();
