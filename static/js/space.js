/* OpsPulse — dynamic space layer for dark mode.
 * Adds a fixed #space-fx overlay (nebula glow, styled in CSS) and periodically
 * launches shooting stars across it. Active only in dark mode and only when the
 * viewer hasn't asked to reduce motion. Pure DOM + Web Animations API — no
 * external assets, air-gapped. */
(() => {
  "use strict";

  const reduced = () =>
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const isDark = () => {
    const t = document.documentElement.getAttribute("data-theme");
    if (t === "dark") return true;
    if (t === "light") return false;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  };

  let fx = null;
  let timer = null;

  function ensureFx() {
    if (fx) return fx;
    fx = document.createElement("div");
    fx.id = "space-fx";
    fx.setAttribute("aria-hidden", "true");
    document.body.appendChild(fx);
    return fx;
  }

  function launch() {
    if (!isDark() || reduced()) return;
    const vw = window.innerWidth, vh = window.innerHeight;
    const el = document.createElement("div");
    el.className = "shooting-star";
    const startX = Math.random() * vw * 0.75;
    const startY = Math.random() * vh * 0.45;
    const angle = 22 + Math.random() * 26;              // downward-right streak
    const dist = vw * 0.45 + Math.random() * vw * 0.45;
    const width = 90 + Math.random() * 90;
    el.style.left = startX + "px";
    el.style.top = startY + "px";
    el.style.width = width + "px";
    ensureFx().appendChild(el);
    const anim = el.animate(
      [
        { transform: `rotate(${angle}deg) translateX(0)`, opacity: 0 },
        { opacity: 1, offset: 0.12 },
        { opacity: 1, offset: 0.78 },
        { transform: `rotate(${angle}deg) translateX(${dist}px)`, opacity: 0 },
      ],
      { duration: 850 + Math.random() * 750, easing: "ease-in" }
    );
    const done = () => el.remove();
    anim.onfinish = done;
    anim.oncancel = done;
  }

  function schedule() {
    clearTimeout(timer);
    const delay = 3500 + Math.random() * 7000;          // ~3.5–10.5s between events
    timer = setTimeout(() => {
      launch();
      if (Math.random() < 0.22) setTimeout(launch, 350); // occasional pair
      schedule();
    }, delay);
  }

  function boot() {
    if (reduced()) return;
    ensureFx();
    schedule();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
