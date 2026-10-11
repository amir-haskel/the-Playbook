/* The Playbook icon set — bundled outline SVGs (no CDN, air-gapped).
 * Modern line icons in a devops vocabulary. Each entry is the inner markup of
 * a 24x24 viewBox; render() wraps it in an <svg> that inherits currentColor.
 *
 * Exposed on window.PlaybookIcons: { ICON_KEYS, render(key, size), has(key) }.
 */
(() => {
  "use strict";

  const ICONS = {
    rocket:
      '<path d="M14 4c3 1 5 3.5 5 8l-3 3H8l-3-3c0-4.5 2-7 5-8"/><path d="M9 15l-2 2-1 4 4-1 2-2"/><circle cx="12" cy="9" r="1.6"/>',
    server:
      '<rect x="3.5" y="4" width="17" height="7" rx="2"/><rect x="3.5" y="13" width="17" height="7" rx="2"/><path d="M7 7.5h.01M7 16.5h.01"/>',
    database:
      '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6"/><path d="M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/>',
    cloud:
      '<path d="M7 18a4 4 0 0 1-.5-8A5.5 5.5 0 0 1 17 9.5a3.5 3.5 0 0 1 0 8.5H7z"/>',
    terminal:
      '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7.5 9l3 3-3 3"/><path d="M13 15h4"/>',
    branch:
      '<circle cx="6" cy="6" r="2.4"/><circle cx="6" cy="18" r="2.4"/><circle cx="18" cy="7.5" r="2.4"/><path d="M6 8.4v7.2"/><path d="M18 10c0 4.2-6 1.8-6 6"/>',
    package:
      '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z"/><path d="M4 7.7l8 4.5 8-4.5"/><path d="M12 12.2V21"/>',
    deploy:
      '<path d="M4 12a8 8 0 0 1 13.7-5.7L20 8"/><path d="M20 4v4h-4"/><path d="M20 12a8 8 0 0 1-13.7 5.7L4 16"/><path d="M4 20v-4h4"/>',
    key:
      '<circle cx="8" cy="12" r="3.6"/><path d="M11.5 12H20"/><path d="M17 12v3"/><path d="M20 12v2.5"/>',
    lock:
      '<rect x="5" y="10.5" width="14" height="9.5" rx="2"/><path d="M8 10.5V7a4 4 0 0 1 8 0v3.5"/>',
    shield:
      '<path d="M12 3l7 3v5.5c0 4.4-3 7.4-7 8.5-4-1.1-7-4.1-7-8.5V6l7-3z"/>',
    settings:
      '<circle cx="12" cy="12" r="3"/><path d="M12 2.5v3M12 18.5v3M3.5 12h3M17.5 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/>',
    play:
      '<path d="M8 5.2v13.6L19 12 8 5.2z"/>',
    upload:
      '<path d="M12 15V4"/><path d="M8 8l4-4 4 4"/><path d="M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3"/>',
    download:
      '<path d="M12 4v11"/><path d="M8 11l4 4 4-4"/><path d="M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3"/>',
    activity:
      '<path d="M3 12h4l3 8 4-16 3 8h4"/>',
    book:
      // Closed hardcover tome (scripture-like): cover + spine hinge, an embossed
      // cross on the face, and a bookmark ribbon hanging from the top edge.
      '<path d="M6.5 4h11a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-11a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/>' +
      '<path d="M8.5 4v16"/>' +
      '<path d="M13.5 10v5M11 12.5h5"/>' +
      '<path d="M14.6 4v4.4l1-.8 1 .8V4"/>',
    moon:
      // Clean crescent for the "switch to dark" control.
      '<path d="M21 12.9A8.6 8.6 0 1 1 11.1 3.1a6.7 6.7 0 0 0 9.9 9.8z"/>',
    sun:
      // Rayed sun for the "switch to light" control.
      '<circle cx="12" cy="12" r="4.1"/>' +
      '<path d="M12 2.4v2.3M12 19.3v2.3M4.4 4.4l1.6 1.6M17.9 17.9l1.6 1.6' +
      'M2.4 12h2.3M19.3 12h2.3M4.4 19.6l1.6-1.6M17.9 6.1l1.6-1.6"/>',
    cpu:
      '<rect x="7" y="7" width="10" height="10" rx="2"/><path d="M10 2.5v3M14 2.5v3M10 18.5v3M14 18.5v3M2.5 10h3M2.5 14h3M18.5 10h3M18.5 14h3"/>',
    layers:
      '<path d="M12 3l9 5-9 5-9-5 9-5z"/><path d="M3 13l9 5 9-5"/>',
    folder:
      '<path d="M4 6.5A2 2 0 0 1 6 4.5h3l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-10z"/>',
    file:
      '<path d="M7 3.5h7l5 5V19a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5.5a2 2 0 0 1 2-2z"/><path d="M14 3.5v5h5"/><path d="M9 13h6M9 16.5h4"/>',
    bell:
      '<path d="M6 9a6 6 0 0 1 12 0c0 4.5 2 5.5 2 5.5H4S6 13.5 6 9z"/><path d="M10 19.5a2 2 0 0 0 4 0"/>',
    users:
      '<circle cx="9" cy="8" r="3"/><path d="M3.5 20a5.5 5.5 0 0 1 11 0"/><path d="M16 5.2a3 3 0 0 1 0 5.6"/><path d="M17.5 14.5a5.5 5.5 0 0 1 3 5.5"/>',
    globe:
      '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c2.7 2.6 2.7 15.4 0 18M12 3c-2.7 2.6-2.7 15.4 0 18"/>',
    zap:
      '<path d="M13 3L5 13.5h6l-1 7.5L18 10.5h-6L13 3z"/>',
    check:
      '<circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/>',
    alert:
      '<path d="M12 4l9 16H3L12 4z"/><path d="M12 10v4.5"/><path d="M12 17.5h.01"/>',
    trash:
      '<path d="M4 7h16"/><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/><path d="M6.5 7l1 12a2 2 0 0 0 2 2h5a2 2 0 0 0 2-2l1-12"/>',
    code:
      '<path d="M8 8l-4 4 4 4"/><path d="M16 8l4 4-4 4"/><path d="M13.5 5l-3 14"/>',
    cube:
      '<path d="M3 8.5l9-5 9 5v7l-9 5-9-5v-7z"/><path d="M3 8.5l9 5 9-5"/><path d="M12 13.5v7"/>',
    gauge:
      '<path d="M4 15a8 8 0 1 1 16 0"/><path d="M12 15l4.5-4.5"/><circle cx="12" cy="15" r="1"/>',
    network:
      '<circle cx="12" cy="5" r="2.2"/><circle cx="5" cy="18" r="2.2"/><circle cx="19" cy="18" r="2.2"/><path d="M12 7.2v4M10.5 12l-4 4M13.5 12l4 4"/>',
    git:
      '<circle cx="12" cy="12" r="9"/><path d="M12 8v8M9 12h6"/>',
    flag:
      '<path d="M6 21V4"/><path d="M6 5h11l-2 3 2 3H6"/>',

    // --- brand / tool logos (simplified monochrome line marks) ---
    docker:
      '<rect x="3.5" y="10.5" width="3" height="3" rx=".4"/><rect x="7.2" y="10.5" width="3" height="3" rx=".4"/><rect x="10.9" y="10.5" width="3" height="3" rx=".4"/><rect x="7.2" y="6.9" width="3" height="3" rx=".4"/><rect x="10.9" y="6.9" width="3" height="3" rx=".4"/><path d="M2.5 14h13.5c.4 2.2-1 3.7-3 4.2-2.4.6-6.6.4-8.5-1.4A5 5 0 0 1 2.5 14z"/><path d="M16 11.5c1-1 2.6-1 3.5 0 .6-.7 1.6-.6 2 0"/>',
    gitlab:
      '<path d="M12 20.5 3.6 12.3l1.4-4.6 2.4 4.6h9.2l2.4-4.6 1.4 4.6z"/>',
    kubernetes:
      '<path d="M12 3l7.2 3.4L21 14l-4.8 6H7.8L3 14l1.8-7.6z"/><circle cx="12" cy="12" r="2.4"/><path d="M12 9.6V4.5M14.2 13.3l3.6 2.6M9.8 13.3l-3.6 2.6M13.8 10.9l3-2.8M10.2 10.9l-3-2.8"/>',
    openshift:
      '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="3"/><path d="M4.6 9 9 10.8M19.4 9 15 10.8M12 20.5V15.2"/>',
    argocd:
      '<circle cx="12" cy="8.5" r="4.8"/><circle cx="10.3" cy="8" r=".6"/><circle cx="13.7" cy="8" r=".6"/><path d="M12 13.3V21M9.2 12.6c-.6 2.6-2 4-3.7 5.6M14.8 12.6c.6 2.6 2 4 3.7 5.6M7.4 11c-1.4 1.7-3 2.4-4.6 3.4M16.6 11c1.4 1.7 3 2.4 4.6 3.4"/>',
    nexus:
      '<path d="M7.2 3.8h9.6L21 8v8l-4.2 4.2H7.2L3 16V8z"/><path d="M9.3 16.2V7.8l5.4 8.4V7.8"/>',
    jenkins:
      '<circle cx="12" cy="7" r="3.4"/><path d="M5.8 21c0-4.1 2.8-7 6.2-7s6.2 2.9 6.2 7"/><path d="M10.4 13.6 12 16.2l1.6-2.6"/>',
    terraform:
      '<path d="M10.3 4.4 4.6 7.7v6.2l5.7 3.3zM11.3 11.1l5.7 3.3V8.2l-5.7-3.3zM11.3 18.1l5.7 3.3v-6.2l-5.7-3.3z"/>',
    helm:
      '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2.4"/><path d="M12 4v3.6M12 16.4V20M4 12h3.6M16.4 12H20M6.3 6.3l2.5 2.5M15.2 15.2l2.5 2.5M17.7 6.3l-2.5 2.5M8.8 15.2l-2.5 2.5"/>',
    github:
      '<path d="M9 19c-4.3 1.4-4.3-2.2-6-2.6m12 4.6v-3.6c0-1 .1-1.4-.5-2 2.9-.3 5.9-1.4 5.9-6.4a5 5 0 0 0-1.4-3.5 4.7 4.7 0 0 0-.1-3.5s-1.1-.4-3.6 1.3a12.3 12.3 0 0 0-6.4 0C6.9 1.5 5.8 1.9 5.8 1.9a4.7 4.7 0 0 0-.1 3.5A5 5 0 0 0 4.3 8.9c0 5 3 6.1 5.9 6.4-.6.6-.6 1.2-.5 2V21"/>',
    linux:
      '<ellipse cx="12" cy="13.5" rx="4.8" ry="5.8"/><path d="M8 8.2C8 5.3 9.7 3.5 12 3.5s4 1.8 4 4.7"/><circle cx="10.4" cy="8" r=".7"/><circle cx="13.6" cy="8" r=".7"/><path d="M10.8 10.4 12 11.4l1.2-1"/><path d="M8.2 19.3 6.6 21.5M15.8 19.3l1.6 2.2"/>',
    ansible:
      '<circle cx="12" cy="12" r="9"/><path d="M11 6.5 16 17.5 8.6 12.4"/>',
    prometheus:
      '<path d="M12 3.5c1.8 2.2 2.3 4-.0 5.8-2.2-1.8-1.7-3.6 0-5.8z"/><circle cx="12" cy="13.5" r="6.5"/><path d="M8 12.2h8M8.6 15.4h6.8"/>',
    vault:
      '<path d="M12 3l7 3v5c0 4.5-3 7.6-7 9-4-1.4-7-4.5-7-9V6z"/><path d="M9 8.5 12 15.5l3-7"/>',
  };

  const ICON_KEYS = Object.keys(ICONS);

  function render(key, size) {
    const inner = ICONS[key] || ICONS.cube;
    const s = size || 20;
    return (
      `<svg viewBox="0 0 24 24" width="${s}" height="${s}" fill="none" ` +
      `stroke="currentColor" stroke-width="1.8" stroke-linecap="round" ` +
      `stroke-linejoin="round" aria-hidden="true">${inner}</svg>`
    );
  }

  window.PlaybookIcons = { ICON_KEYS, render, has: (k) => k in ICONS };
})();
