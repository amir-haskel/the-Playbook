/* The Playbook — night sky for dark mode: two parallax star layers + meteors.
 *
 * Design notes (why it looks the way it does):
 *
 *  - TWO MOVING LAYERS. A far layer (many, smaller, slower) and a near layer
 *    (fewer, brighter, faster). The speed difference is the depth cue, and both
 *    layers move at a speed you can actually notice if you look for a few
 *    seconds. Nothing is static: a motionless, ultra-faint speck reads as dust
 *    on the screen, not as a star.
 *  - STARS ARE POINTS WITH FLARE, NOT BALLS. Each star is a pre-rendered sprite
 *    with a small hard core, a TIGHT halo, and — on the brighter ones —
 *    diffraction spikes (4 points, 8 for the brightest). Those spikes are what
 *    make the eye read "star" instead of "soft round dot".
 *  - BRIGHT ENOUGH TO BE THE SUBJECT. This is a clear, dark-sky night: plenty
 *    of clearly visible stars, with a steep magnitude spread so a handful blaze
 *    and the rest recede.
 *  - STARS ARE WHITE, with only a whisper of stellar temperature (blue-white /
 *    faint amber). Saturated stars look like confetti.
 *  - SCINTILLATION SCALES WITH BRIGHTNESS: bright stars twinkle visibly, faint
 *    ones sit steady, all out of phase.
 *  - METEORS are white, thin and mostly haze — a long, slow, rare streak with a
 *    small soft head, so catching one feels like a glimpse rather than a line
 *    drawn across the UI.
 *
 * Dark-mode only, motion-safe (prefers-reduced-motion => one static draw, no
 * meteors), fully procedural: canvas gradients only, NO images (air-gapped).
 */
(() => {
  "use strict";

  const mqlMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const mqlDark = window.matchMedia("(prefers-color-scheme: dark)");

  const reduced = () => mqlMotion.matches;
  const isDark = () => {
    const t = document.documentElement.getAttribute("data-theme");
    if (t === "dark") return true;
    if (t === "light") return false;
    return mqlDark.matches; // "system": follow OS preference
  };
  const active = () => isDark() && !reduced();

  const rand = (min, max) => min + Math.random() * (max - min);
  // Bell-ish random in [-1,1] — natural scatter instead of flat uniform.
  const bell = () => (Math.random() + Math.random() + Math.random() - 1.5) / 1.5;

  /* ------------------------------------------------------------------ stars */

  // Near-white tints; cool dominates (most naked-eye stars are white/blue-white).
  const TINTS = [
    { rgb: [255, 255, 255], w: 0.5 },
    { rgb: [214, 229, 255], w: 0.36 }, // blue-white
    { rgb: [255, 236, 212], w: 0.14 }, // faint amber
  ];
  // Core radii (CSS px) — fine and hard; the flare does the visual work. Kept
  // small so a dense field reads as distant points, not dots.
  const CORES = [0.3, 0.38, 0.48, 0.6, 0.76, 0.98];
  // Magnitude spread per layer. Far = mostly modest; near carries the standouts.
  const FAR_WEIGHTS = [0.34, 0.26, 0.2, 0.12, 0.06, 0.02];
  const NEAR_WEIGHTS = [0.06, 0.12, 0.2, 0.26, 0.24, 0.12];

  // Counts at a 1920x1080 reference viewport (scaled by area below). A rich but
  // airy field — many fine stars given room to breathe rather than clumped.
  const REF_AREA = 1920 * 1080;
  const FAR_AT_REF = 380;
  const NEAR_AT_REF = 105;

  // Faint star-dust haze ("Milky Way" hint) — a diagonal band behind the stars.
  const BAND_ANGLE = (-21 * Math.PI) / 180;

  let canvas = null;
  let ctx = null;
  let width = 0;
  let height = 0;
  let dpr = 1;
  let stars = [];
  let sprites = []; // [tint][core] -> pre-rendered star sprite
  let haze = null;
  let clusters = [];
  let raf = 0;
  let last = 0;

  function pickWeighted(weights) {
    let r = Math.random();
    for (let i = 0; i < weights.length; i += 1) {
      r -= weights[i];
      if (r <= 0) return i;
    }
    return weights.length - 1;
  }

  /* One star = hard core + tight halo + diffraction spikes. The spikes are the
   * difference between "star" and "round blob"; they appear on the brighter
   * half and go 8-point on the very brightest. Pre-rendered per (tint, size)
   * bucket so the frame loop only does drawImage. */
  function makeSprite(rgb, core) {
    const halo = core * 4.2 + 1.5; // tight — a point of light, not a ball
    const spikes = core >= 0.64 ? (core >= 1.0 ? 8 : 4) : 0;
    const spikeLen = halo * (core >= 1.0 ? 2.9 : 2.3);
    const r = Math.ceil(Math.max(halo, spikes ? spikeLen : 0)) + 1;
    const size = r * 2;
    const c = document.createElement("canvas");
    c.width = size;
    c.height = size;
    const g = c.getContext("2d");
    const s = rgb[0] + "," + rgb[1] + "," + rgb[2];

    // Diffraction spikes first, so the core glow sits on top of their roots.
    if (spikes) {
      const w = 0.5 + core * 0.18;
      const aMain = 0.22;
      g.save();
      g.translate(r, r);
      for (let i = 0; i < spikes; i += 1) {
        const long = i < 4; // the 4 primary points are longer
        const len = spikeLen * (long ? 1 : 0.58);
        g.save();
        g.rotate((Math.PI / 2) * i + (spikes === 8 && !long ? Math.PI / 4 : 0));
        const lg = g.createLinearGradient(0, 0, len, 0);
        lg.addColorStop(0, "rgba(" + s + "," + aMain * (long ? 1 : 0.7) + ")");
        lg.addColorStop(0.45, "rgba(" + s + "," + aMain * 0.28 + ")");
        lg.addColorStop(1, "rgba(" + s + ",0)");
        g.fillStyle = lg;
        g.beginPath();
        g.moveTo(0, -w);
        g.lineTo(len, 0);
        g.lineTo(0, w);
        g.closePath();
        g.fill();
        g.restore();
      }
      g.restore();
    }

    const grad = g.createRadialGradient(r, r, 0, r, r, halo);
    grad.addColorStop(0, "rgba(255,255,255,1)");
    grad.addColorStop(Math.min(core / halo, 0.85), "rgba(" + s + ",0.9)");
    // Fast falloff => a crisp point rather than a disc.
    grad.addColorStop(Math.min((core * 1.6) / halo, 0.93), "rgba(" + s + ",0.2)");
    grad.addColorStop(Math.min((core * 2.8) / halo, 0.98), "rgba(" + s + ",0.05)");
    grad.addColorStop(1, "rgba(" + s + ",0)");
    g.fillStyle = grad;
    g.beginPath();
    g.arc(r, r, halo, 0, Math.PI * 2);
    g.fill();

    return { canvas: c, r: r };
  }

  function buildSprites() {
    sprites = TINTS.map((t) => CORES.map((core) => makeSprite(t.rgb, core)));
  }

  /* Loose clumps + voids, so the initial sky is not an even sprinkle. (Stars
   * respawn uniformly as they drift through, which is fine — a random field
   * already reads natural; the clumping just makes the first look better.) */
  function buildClusters() {
    clusters = [];
    const n = 7 + Math.floor(Math.random() * 4);
    for (let i = 0; i < n; i += 1) {
      clusters.push({
        x: rand(0, width),
        y: rand(0, height),
        r: rand(0.09, 0.2) * Math.min(width, height),
      });
    }
  }

  function scatterPoint() {
    // Mostly uniform, only a light bias toward clusters — an evenly spread sky
    // rather than obvious clumps and voids.
    if (clusters.length && Math.random() < 0.2) {
      const c = clusters[Math.floor(Math.random() * clusters.length)];
      return { x: c.x + bell() * c.r, y: c.y + bell() * c.r };
    }
    return { x: rand(0, width), y: rand(0, height) };
  }

  /* Pre-rendered haze band: a few elongated, very low-alpha blobs along a
   * diagonal. Purely a backdrop suggestion of unresolved light — it has no
   * features, so it can sit still behind the drifting stars unnoticed. */
  function buildHaze() {
    haze = document.createElement("canvas");
    haze.width = Math.max(1, Math.round(width));
    haze.height = Math.max(1, Math.round(height));
    const g = haze.getContext("2d");
    const cx = width * 0.5;
    const cy = height * 0.44;
    const ux = Math.cos(BAND_ANGLE);
    const uy = Math.sin(BAND_ANGLE);
    const span = Math.hypot(width, height) * 0.6;

    g.globalCompositeOperation = "lighter";
    const blobs = 9;
    for (let i = 0; i < blobs; i += 1) {
      const t = (i / (blobs - 1) - 0.5) * 2 * span;
      const x = cx + ux * t + -uy * bell() * height * 0.05;
      const y = cy + uy * t + ux * bell() * height * 0.05;
      const len = rand(0.16, 0.3) * Math.hypot(width, height);
      const wid = rand(0.1, 0.19) * height;
      const alpha = rand(0.012, 0.024);
      g.save();
      g.translate(x, y);
      g.rotate(BAND_ANGLE);
      g.scale(len / wid, 1); // elongate along the band
      const rg = g.createRadialGradient(0, 0, 0, 0, 0, wid);
      rg.addColorStop(0, "rgba(226,234,255," + alpha + ")");
      rg.addColorStop(0.5, "rgba(214,226,255," + alpha * 0.42 + ")");
      rg.addColorStop(1, "rgba(210,222,255,0)");
      g.fillStyle = rg;
      g.beginPath();
      g.arc(0, 0, wid, 0, Math.PI * 2);
      g.fill();
      g.restore();
    }
    g.globalCompositeOperation = "source-over";
  }

  function resetStar(star, initial) {
    if (initial) {
      const p = scatterPoint();
      star.x = p.x;
      star.y = p.y;
    } else {
      // Re-enter from just off the top/left edge, opposite the drift.
      if (Math.random() < 0.72) {
        star.x = rand(-40, width + 40);
        star.y = rand(-60, -8);
      } else {
        star.x = rand(-60, -8);
        star.y = rand(-40, height);
      }
    }
    star.tint = pickWeighted(TINTS.map((t) => t.w));
    star.core = pickWeighted(star.near ? NEAR_WEIGHTS : FAR_WEIGHTS);
    // Bright enough to be the subject of the page, not a texture behind it.
    // Lifted floors so even the far layer reads as luminous, not dust.
    star.alpha = star.near ? rand(0.8, 1) : rand(0.5, 0.85);
    // Steady, coherent drift, px/second (time-scaled in frame()) — the whole
    // field slides the same way, like a night-sky timelapse panning across the
    // heavens: brisk, but never a blur. The near layer moves clearly faster
    // than the far one — that difference is the depth.
    if (star.near) {
      star.vx = rand(5.8, 10.2);
      star.vy = rand(8.6, 16);
    } else {
      star.vx = rand(2.4, 4.8);
      star.vy = rand(3.5, 7.4);
    }
    // Bright stars scintillate visibly; faint ones stay steady.
    star.twAmp = 0.05 + star.core * 0.06;
    star.twSpeed = rand(0.1, 0.35);
    star.twPhase = rand(0, Math.PI * 2);
  }

  function build() {
    const scale = Math.max(0.35, (width * height) / REF_AREA);
    buildClusters();
    stars = [];
    const far = Math.round(FAR_AT_REF * scale);
    const near = Math.round(NEAR_AT_REF * scale);
    for (let i = 0; i < far; i += 1) {
      const s = { near: false };
      resetStar(s, true);
      stars.push(s);
    }
    for (let i = 0; i < near; i += 1) {
      const s = { near: true };
      resetStar(s, true);
      stars.push(s);
    }
  }

  function drawStar(star, time) {
    const sprite = sprites[star.tint][star.core];
    const a =
      star.alpha *
      (1 + Math.sin(time * star.twSpeed * Math.PI * 2 + star.twPhase) * star.twAmp);
    if (a <= 0.008) return;
    ctx.globalAlpha = a > 1 ? 1 : a;
    ctx.drawImage(sprite.canvas, star.x - sprite.r, star.y - sprite.r);
  }

  /* ---------------------------------------------------------------- meteors */

  let meteors = [];
  let nextMeteor = 0;

  function spawnMeteor() {
    const leftward = Math.random() < 0.45;
    const deg = leftward ? rand(115, 150) : rand(30, 65);
    const a = (deg * Math.PI) / 180;
    meteors.push({
      x: leftward ? rand(width * 0.55, width * 1.02) : rand(-width * 0.02, width * 0.45),
      y: rand(-height * 0.05, height * 0.3),
      ux: Math.cos(a),
      uy: Math.sin(a),
      speed: rand(105, 185), // px/s — unhurried
      life: rand(3.6, 5.4), // s, including the long fade
      t: 0,
      maxLen: rand(230, 430), // long, but nearly all of it is faint haze
      hw: rand(0.42, 0.8), // thin core
      peak: rand(0.3, 0.52), // never dominant
    });
  }

  function drawMeteor(m) {
    const p = m.t / m.life;
    // Slow rise, brief crest, long graceful decay.
    let env;
    if (p < 0.2) env = p / 0.2;
    else if (p > 0.42) env = Math.max(0, 1 - (p - 0.42) / 0.58);
    else env = 1;
    env = env * env * (3 - 2 * env); // smoothstep
    const alpha = env * m.peak;
    if (alpha <= 0.006) return;

    const len = m.maxLen * (0.45 + 0.55 * env);
    const hx = m.x;
    const hy = m.y;
    const tx = hx - m.ux * len;
    const ty = hy - m.uy * len;
    const px = -m.uy;
    const py = m.ux;

    // White ionisation trail — no hue, and it drops off fast so the streak is a
    // suggestion of light rather than a drawn line.
    const grad = ctx.createLinearGradient(hx, hy, tx, ty);
    grad.addColorStop(0, "rgba(255,255,255," + alpha + ")");
    grad.addColorStop(0.05, "rgba(240,246,255," + alpha * 0.62 + ")");
    grad.addColorStop(0.2, "rgba(228,238,255," + alpha * 0.22 + ")");
    grad.addColorStop(0.5, "rgba(220,232,255," + alpha * 0.07 + ")");
    grad.addColorStop(0.8, "rgba(216,228,255," + alpha * 0.02 + ")");
    grad.addColorStop(1, "rgba(214,226,255,0)");
    ctx.fillStyle = grad;

    // Mostly haze: a wide, very transparent taper carries the light...
    ctx.globalAlpha = 0.22;
    ctx.beginPath();
    ctx.moveTo(hx + px * m.hw * 5, hy + py * m.hw * 5);
    ctx.lineTo(hx - px * m.hw * 5, hy - py * m.hw * 5);
    ctx.lineTo(tx, ty);
    ctx.closePath();
    ctx.fill();

    // ...with a thin, delicate core inside it.
    ctx.globalAlpha = 0.85;
    ctx.beginPath();
    ctx.moveTo(hx + px * m.hw, hy + py * m.hw);
    ctx.lineTo(hx - px * m.hw, hy - py * m.hw);
    ctx.lineTo(tx, ty);
    ctx.closePath();
    ctx.fill();

    // Small soft head — a glow, not a headlamp.
    ctx.globalAlpha = 1;
    const bloom = m.hw * 5.5;
    const hg = ctx.createRadialGradient(hx, hy, 0, hx, hy, bloom);
    hg.addColorStop(0, "rgba(255,255,255," + alpha * 0.9 + ")");
    hg.addColorStop(0.3, "rgba(234,242,255," + alpha * 0.3 + ")");
    hg.addColorStop(1, "rgba(224,236,255,0)");
    ctx.fillStyle = hg;
    ctx.beginPath();
    ctx.arc(hx, hy, bloom, 0, Math.PI * 2);
    ctx.fill();
  }

  function stepMeteors(dt, time) {
    if (time >= nextMeteor) {
      spawnMeteor();
      // Rare — part of what makes catching one feel like something.
      nextMeteor = time + (Math.random() < 0.06 ? rand(0.6, 1.4) : rand(9, 20));
    }
    for (let i = meteors.length - 1; i >= 0; i -= 1) {
      const m = meteors[i];
      m.t += dt;
      const v = m.speed * (1 + 0.22 * (m.t / m.life)); // gentle acceleration
      m.x += m.ux * v * dt;
      m.y += m.uy * v * dt;
      if (m.t >= m.life) meteors.splice(i, 1);
      else drawMeteor(m);
    }
  }

  /* ----------------------------------------------------------------- canvas */

  function ensureCanvas() {
    if (canvas) return;
    canvas = document.createElement("canvas");
    canvas.id = "starfield";
    canvas.setAttribute("aria-hidden", "true");
    document.body.appendChild(canvas);
    ctx = canvas.getContext("2d", { alpha: true });
  }

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    const root = document.documentElement;
    const w = window.innerWidth || root.clientWidth || 0;
    const h = window.innerHeight || root.clientHeight || 0;
    // Some embedders report a 0-sized viewport until layout settles. Building a
    // 0x0 sky would leave the canvas permanently blank, so wait for a real size
    // (the ResizeObserver in boot() calls back once there is one).
    if (w < 2 || h < 2) return;
    width = w;
    height = h;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    canvas.style.width = width + "px";
    canvas.style.height = height + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    buildHaze();
    build();
    if (!raf) drawStatic();
  }

  function paintSky(time) {
    ctx.clearRect(0, 0, width, height);
    // Additive, so overlapping halos and the haze build up light.
    ctx.globalCompositeOperation = "lighter";
    ctx.globalAlpha = 1;
    if (haze) ctx.drawImage(haze, 0, 0, width, height);
    for (const s of stars) drawStar(s, time);
    ctx.globalAlpha = 1;
  }

  function drawStatic() {
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    if (!isDark()) return;
    paintSky(0);
    ctx.globalCompositeOperation = "source-over";
  }

  function frame(t) {
    const time = t / 1000;
    const dt = Math.min((t - last) / 1000, 0.05);
    last = t;

    paintSky(time);
    for (const s of stars) {
      s.x += s.vx * dt;
      s.y += s.vy * dt;
      if (s.x > width + 40 || s.y > height + 40) resetStar(s, false);
    }

    stepMeteors(dt, time);

    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
    raf = requestAnimationFrame(frame);
  }

  function start() {
    if (raf) return;
    last = performance.now();
    nextMeteor = last / 1000 + rand(2.5, 6); // one fairly soon, then rare
    raf = requestAnimationFrame(frame);
  }

  function stop() {
    if (raf) {
      cancelAnimationFrame(raf);
      raf = 0;
    }
    meteors = [];
    if (ctx) ctx.clearRect(0, 0, width, height);
  }

  // Start/stop with theme + motion preference so no CPU is burned while the
  // sky is hidden (light mode) or motion is reduced.
  function update() {
    if (active()) {
      start();
    } else {
      stop();
      if (isDark() && reduced()) drawStatic();
    }
  }

  function boot() {
    ensureCanvas();
    buildSprites();
    resize();
    update();
    const onResize = () => {
      const before = width + "x" + height;
      resize();
      if (before !== width + "x" + height) update(); // (re)start once we have a size
      if (!raf && isDark() && reduced()) drawStatic();
    };
    window.addEventListener("resize", onResize, { passive: true });
    // Also observe the root element: it fires when the viewport becomes known
    // even if no window resize event does.
    if (window.ResizeObserver) new ResizeObserver(onResize).observe(document.documentElement);
    new MutationObserver(update).observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    const onChange = () => update();
    if (mqlDark.addEventListener) mqlDark.addEventListener("change", onChange);
    else if (mqlDark.addListener) mqlDark.addListener(onChange);
    if (mqlMotion.addEventListener) mqlMotion.addEventListener("change", onChange);
    else if (mqlMotion.addListener) mqlMotion.addListener(onChange);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
