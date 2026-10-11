/* Light/dark theme toggle with persistence. A tiny pre-paint snippet in each
 * page's <head> applies the saved theme before first paint (no flash); this
 * file wires the toggle button and keeps the icon in sync. */
(() => {
  "use strict";
  const KEY = "playbook-theme";

  const systemDark = () =>
    window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;

  const current = () =>
    document.documentElement.getAttribute("data-theme") ||
    (systemDark() ? "dark" : "light");

  function apply(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem(KEY, theme); } catch (_) {}
    updateButton(theme);
  }

  function updateButton(theme) {
    const btn = document.getElementById("theme-toggle");
    if (!btn) return;
    const dark = theme === "dark";
    // Show the icon of the mode you'd switch TO: sun in dark, moon in light.
    const key = dark ? "sun" : "moon";
    btn.innerHTML = window.PlaybookIcons ? window.PlaybookIcons.render(key, 21) : (dark ? "☀" : "☾");
    btn.setAttribute("aria-label", `Switch to ${dark ? "light" : "dark"} mode`);
    btn.title = `Switch to ${dark ? "light" : "dark"} mode`;
  }

  function toggle() { apply(current() === "dark" ? "light" : "dark"); }

  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("theme-toggle");
    if (btn) btn.addEventListener("click", toggle);
    updateButton(current());
  });

  // React to OS changes only while the user hasn't made an explicit choice.
  if (window.matchMedia) {
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
      let saved = null;
      try { saved = localStorage.getItem(KEY); } catch (_) {}
      if (!saved) updateButton(current());
    });
  }
})();
