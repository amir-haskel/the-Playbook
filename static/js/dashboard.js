/* OpsPulse dashboard: unified card grid, tag filter chips, execution modal,
 * SSE streaming. Tags carry the color; icons are bundled SVGs. */
(() => {
  "use strict";

  const API = "/api/v1";
  let actions = [];
  let tags = [];               // [{id,name,color,type}]
  let activeFunc = null;       // one function tag id, or null
  let activeTeam = null;       // one team tag id, or null
  let current = null;          // action open in the modal
  let currentExecId = null;    // execution id currently shown/streamed in the modal
  let eventSource = null;
  let historyTimer = null;     // polling interval while the drawer is open
  let historyLimit = 50;       // configurable retention cap (from /settings)
  const dynState = {};         // paramName -> "loading" | "ok" | "error"

  const el = (id) => document.getElementById(id);
  const board = el("board");
  const filterBar = el("filter-bar");
  const search = el("search");
  const modal = el("modal");
  const icon = (key, size) => (window.OpsIcons ? window.OpsIcons.render(key, size) : "");
  const tagClass = (color) => "tag-" + (color || "slate");

  // ---------------------------------------------------------------- load
  async function load() {
    try {
      const [aRes, tRes] = await Promise.all([
        fetch(`${API}/actions`),
        fetch(`${API}/tags`),
      ]);
      actions = await aRes.json();
      tags = await tRes.json();
      renderFilters();
      render();
    } catch (e) {
      board.innerHTML = `<div class="empty">Failed to load actions.</div>`;
    }
    try {
      const s = await (await fetch(`${API}/settings`)).json();
      if (s && s.history_limit) historyLimit = s.history_limit;
    } catch (_) { /* keep default */ }
  }

  // ---------------------------------------------------------------- filters
  const funcTags = () => tags.filter((t) => t.type !== "team");
  const teamTags = () => tags.filter((t) => t.type === "team");

  function renderFilters() {
    filterBar.innerHTML = "";
    filterBar.appendChild(allChip());
    for (const t of funcTags()) filterBar.appendChild(funcChip(t));
    if (teamTags().length) {
      const sep = document.createElement("span");
      sep.className = "filter-sep";
      filterBar.appendChild(sep);
      for (const t of teamTags()) filterBar.appendChild(teamChip(t));
    }
  }

  function allChip() {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip chip-all" + (!activeFunc && !activeTeam ? " active" : "");
    b.textContent = "All";
    b.addEventListener("click", () => { activeFunc = null; activeTeam = null; renderFilters(); render(); });
    return b;
  }

  function funcChip(t) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip " + tagClass(t.color) + (activeFunc === t.id ? " active" : "");
    b.textContent = t.name;
    b.addEventListener("click", () => {
      activeFunc = activeFunc === t.id ? null : t.id;   // single-select
      renderFilters(); render();
    });
    return b;
  }

  function teamChip(t) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip chip-team" + (activeTeam === t.id ? " active" : "");
    b.textContent = t.name;
    b.addEventListener("click", () => {
      activeTeam = activeTeam === t.id ? null : t.id;   // single-select
      renderFilters(); render();
    });
    return b;
  }

  // ---------------------------------------------------------------- grid
  function render() {
    const q = search.value.trim().toLowerCase();
    const filtered = actions.filter((a) => {
      const ids = a.tags || [];
      // Function + team combine with AND: an action must carry each selected one.
      if (activeFunc && !ids.includes(activeFunc)) return false;
      if (activeTeam && !ids.includes(activeTeam)) return false;
      if (!q) return true;
      const tagNames = (a.tag_details || []).map((t) => t.name).join(" ").toLowerCase();
      return (
        (a.title || "").toLowerCase().includes(q) ||
        (a.description || "").toLowerCase().includes(q) ||
        tagNames.includes(q)
      );
    });

    if (!filtered.length) {
      board.innerHTML = `<div class="empty">${
        actions.length ? "No actions match your filter." :
        "No actions configured yet. Head to <a href='/admin'>Admin</a> to create one."
      }</div>`;
      return;
    }

    const grid = document.createElement("div");
    grid.className = "grid";
    for (const a of filtered) grid.appendChild(cardEl(a));
    board.innerHTML = "";
    board.appendChild(grid);
  }

  function cardEl(a) {
    const details = a.tag_details || [];
    const func = details.find((t) => t.type !== "team");
    const team = details.find((t) => t.type === "team");
    const card = document.createElement("div");
    card.className = "card" + (func ? " " + tagClass(func.color) : "");
    const funcPill = func
      ? `<div class="card-tags"><span class="tag-pill ${tagClass(func.color)}">${escapeHtml(func.name)}</span></div>`
      : "";
    const teamBadge = team ? `<span class="team-badge">${escapeHtml(team.name)}</span>` : "";
    card.innerHTML = `
      <div class="card-head">
        <div class="card-icon">${icon(a.icon, 22)}</div>
        ${teamBadge}
      </div>
      <div class="card-title">${escapeHtml(a.title)}</div>
      <div class="card-desc">${escapeHtml(a.description || "")}</div>
      ${funcPill}`;
    card.addEventListener("click", () => openModal(a));
    return card;
  }

  // ---------------------------------------------------------------- modal
  function openModal(a) {
    current = a;
    currentExecId = null;
    closeStream();
    Object.keys(dynState).forEach((k) => delete dynState[k]);
    const func = (a.tag_details || []).find((t) => t.type !== "team");
    const iconBox = el("m-icon");
    iconBox.className = "card-icon" + (func ? " " + tagClass(func.color) : "");
    iconBox.innerHTML = icon(a.icon, 24);
    el("m-title").textContent = a.title;
    el("m-desc").textContent = a.description || "";
    el("m-run").classList.add("hidden");
    el("m-terminal").innerHTML = "";
    el("m-artifacts").innerHTML = "";
    setStatus("PENDING");
    buildForm(a);
    gateExecute();
    modal.classList.add("open");
  }

  function closeModal() {
    modal.classList.remove("open", "docked");
    closeStream();
    current = null;
  }

  function buildForm(a) {
    const form = el("m-form");
    form.innerHTML = "";
    if (!a.parameters || !a.parameters.length) {
      form.innerHTML = `<div class="muted small">This action takes no inputs.</div>`;
      return;
    }
    for (const p of a.parameters) form.appendChild(fieldEl(a, p));
    // Re-evaluate the Execute gate as the user fills the form.
    form.addEventListener("input", gateExecute);
    form.addEventListener("change", gateExecute);
  }

  function fieldEl(action, p) {
    const wrap = document.createElement("div");
    wrap.className = "field";
    const label = p.label || p.name;
    const req = p.required ? ' <span class="req">*</span>' : "";
    const id = "f_" + p.name;

    if (p.type === "checkbox") {
      if (p.options && p.options.length) {
        // Multi-select checkbox group.
        const defaults = String(p.default ?? "").split(",").map((s) => s.trim()).filter(Boolean);
        wrap.innerHTML = `<label>${escapeHtml(label)}${req}</label>`;
        const group = document.createElement("div");
        group.className = "radio-row";
        group.innerHTML = p.options.map((o) =>
          `<label><input type="checkbox" name="cb_${p.name}" value="${escapeAttr(o)}" ${
            defaults.includes(o) ? "checked" : ""}/> ${escapeHtml(o)}</label>`).join("");
        wrap.appendChild(group);
        return wrap;
      }
      wrap.innerHTML = `<div class="check-row">
        <input type="checkbox" id="${id}" data-name="${p.name}" ${truthy(p.default) ? "checked" : ""}/>
        <label for="${id}" style="margin:0;">${escapeHtml(label)}${req}</label></div>`;
      return wrap;
    }

    if (p.type === "file") {
      wrap.innerHTML = `<label>${escapeHtml(label)}${req}</label>`;
      wrap.appendChild(dropzoneEl(p));
      return wrap;
    }

    wrap.innerHTML = `<label for="${id}">${escapeHtml(label)}${req}</label>`;

    if (p.type === "select" || p.type === "dynamic_select") {
      const sel = document.createElement("select");
      sel.id = id; sel.dataset.name = p.name;
      if (p.type === "dynamic_select") {
        sel.innerHTML = `<option value="">Loading options…</option>`;
        loadDynamic(action, p, sel);
      } else {
        sel.innerHTML = `<option value="">— select —</option>` +
          (p.options || []).map((o) => `<option value="${escapeAttr(o)}">${escapeHtml(o)}</option>`).join("");
        if (p.default) sel.value = p.default;
      }
      wrap.appendChild(sel);
    } else if (p.type === "radio") {
      const row = document.createElement("div");
      row.className = "radio-row";
      row.dataset.name = p.name;
      row.innerHTML = (p.options || []).map((o, i) =>
        `<label><input type="radio" name="${id}" value="${escapeAttr(o)}" ${
          (p.default === o || (!p.default && i === 0)) ? "checked" : ""
        }/> ${escapeHtml(o)}</label>`).join("");
      wrap.appendChild(row);
    } else {
      const input = document.createElement("input");
      input.type = p.type === "number" ? "number" : "text";
      if (p.type === "number") input.min = "0";
      input.id = id; input.dataset.name = p.name;
      if (p.default != null) input.value = p.default;
      wrap.appendChild(input);
    }
    return wrap;
  }

  // File dropzone: drag-and-drop or click-to-browse, uploads immediately and
  // stores the returned token on the element for collectValues/gating.
  function dropzoneEl(p) {
    const zone = document.createElement("div");
    zone.className = "dropzone";
    zone.dataset.name = p.name;
    const input = document.createElement("input");
    input.type = "file";
    input.className = "dropzone-input";
    input.style.display = "none";
    zone.innerHTML = `<div class="dropzone-hint">Drop a file here or click to browse</div>`;
    zone.appendChild(input);

    const pickFile = (file) => { if (file) uploadFile(zone, input, file); };

    zone.addEventListener("click", (e) => {
      if (e.target.closest(".file-clear")) return;
      input.click();
    });
    input.addEventListener("change", () => pickFile(input.files[0]));
    zone.addEventListener("dragover", (e) => {
      e.preventDefault();
      zone.classList.add("dragover");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("dragover");
      pickFile(e.dataTransfer.files[0]);
    });
    return zone;
  }

  async function uploadFile(zone, input, file) {
    clearZoneError(zone);
    zone.classList.add("uploading");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API}/upload`, { method: "POST", body: fd });
      if (!res.ok) throw new Error(await readErr(res, "Upload failed"));
      const body = await res.json();
      zone.dataset.token = body.token || "";
      showZoneFile(zone, body.filename || file.name);
    } catch (e) {
      delete zone.dataset.token;
      showZoneError(zone, e.message);
    } finally {
      zone.classList.remove("uploading");
      input.value = "";        // allow re-selecting the same file
      gateExecute();
    }
  }

  function showZoneFile(zone, filename) {
    zone.querySelector(".dropzone-file")?.remove();
    const chip = document.createElement("div");
    chip.className = "dropzone-file";
    chip.innerHTML = `${escapeHtml(filename)}<button type="button" class="file-clear" aria-label="Remove">×</button>`;
    chip.querySelector(".file-clear").addEventListener("click", (e) => {
      e.stopPropagation();
      delete zone.dataset.token;
      chip.remove();
      gateExecute();
    });
    zone.appendChild(chip);
  }

  function showZoneError(zone, msg) {
    clearZoneError(zone);
    const err = document.createElement("div");
    err.className = "dropzone-error small err-text";
    err.textContent = msg;
    zone.appendChild(err);
  }
  function clearZoneError(zone) { zone.querySelector(".dropzone-error")?.remove(); }

  async function loadDynamic(action, p, sel) {
    dynState[p.name] = "loading";
    gateExecute();
    try {
      const url = `${API}/dynamic-options/${encodeURIComponent(p.dynamic_type || "custom")}` +
        `?action_id=${encodeURIComponent(action.id)}&param=${encodeURIComponent(p.name)}`;
      const res = await fetch(url);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(errText(body, res.statusText));
      }
      const opts = await res.json();
      if (!opts.length) {
        sel.innerHTML = `<option value="">(no options returned)</option>`;
        dynState[p.name] = "error";   // nothing selectable -> block execution
      } else {
        sel.innerHTML = `<option value="">— select —</option>` +
          opts.map((o) => `<option value="${escapeAttr(o.value)}">${escapeHtml(o.label)}</option>`).join("");
        if (p.default) sel.value = p.default;
        dynState[p.name] = "ok";
      }
    } catch (e) {
      sel.innerHTML = `<option value="">⚠ ${escapeHtml(e.message)}</option>`;
      dynState[p.name] = "error";
    }
    gateExecute();
  }

  // Enable Execute only when required fields are filled and every dynamic
  // dropdown has loaded successfully.
  function gateExecute() {
    let reason = "";
    for (const p of (current && current.parameters) || []) {
      if (p.type === "dynamic_select") {
        const st = dynState[p.name];
        if (st === "loading") { reason = "Loading options…"; break; }
        if (st === "error") { reason = `"${p.label || p.name}" couldn't load`; break; }
      }
      if (p.required && paramEmpty(p)) { reason = `Fill required field: ${p.label || p.name}`; break; }
    }
    el("m-execute").disabled = !!reason;
    const note = el("m-gate");
    note.textContent = reason;
    note.classList.toggle("hidden", !reason);
  }

  function paramEmpty(p) {
    if (p.type === "checkbox") {
      if (p.options && p.options.length) {
        return document.querySelectorAll(`input[name="cb_${p.name}"]:checked`).length === 0;
      }
      const node = el("f_" + p.name);
      return !(node && node.checked);
    }
    if (p.type === "radio") {
      return !document.querySelector(`input[name="f_${p.name}"]:checked`);
    }
    if (p.type === "file") {
      const zone = document.querySelector(`.dropzone[data-name="${p.name}"]`);
      return !(zone && zone.dataset.token);
    }
    const node = el("f_" + p.name);
    return !node || String(node.value).trim() === "";
  }

  function collectValues() {
    const values = {};
    if (!current.parameters) return values;
    for (const p of current.parameters) {
      if (p.type === "checkbox") {
        if (p.options && p.options.length) {
          values[p.name] = [...document.querySelectorAll(`input[name="cb_${p.name}"]:checked`)]
            .map((n) => n.value);
        } else {
          values[p.name] = el("f_" + p.name).checked;
        }
      } else if (p.type === "radio") {
        const chosen = document.querySelector(`input[name="f_${p.name}"]:checked`);
        values[p.name] = chosen ? chosen.value : "";
      } else if (p.type === "file") {
        const zone = document.querySelector(`.dropzone[data-name="${p.name}"]`);
        values[p.name] = (zone && zone.dataset.token) || "";
      } else {
        const node = el("f_" + p.name);
        values[p.name] = node ? node.value : "";
      }
    }
    return values;
  }

  // ---------------------------------------------------------------- execute
  async function execute() {
    if (!current) return;
    const btn = el("m-execute");
    btn.disabled = true;
    currentExecId = null;
    el("m-run").classList.remove("hidden");
    el("m-terminal").innerHTML = "";
    el("m-artifacts").innerHTML = "";
    setStatus("PENDING");

    let execId;
    try {
      const res = await fetch(`${API}/execute/${current.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ values: collectValues() }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(errText(body, "Execution failed to start"));
      execId = body.execution_id;
    } catch (e) {
      appendLine(e.message, "err");
      setStatus("FAILED");
      gateExecute();
      return;
    }
    stream(execId);
    refreshHistory();   // reflect the new run in the drawer if it's open
  }

  function stream(execId) {
    closeStream();
    currentExecId = execId;
    setStatus("RUNNING");
    eventSource = new EventSource(`${API}/stream/${execId}`);
    eventSource.addEventListener("stdout", (e) => appendLine(JSON.parse(e.data).line));
    eventSource.addEventListener("stderr", (e) => appendLine(JSON.parse(e.data).line, "err"));
    eventSource.addEventListener("status", (e) => {
      const data = JSON.parse(e.data);
      setStatus(data.status);
      renderArtifacts(data.artifacts || []);
      closeStream();
      gateExecute();
      refreshHistory();
    });
    eventSource.onerror = () => {
      if (el("m-status").dataset.state === "RUNNING") appendLine("[connection closed]", "sys");
      closeStream();
    };
  }

  function closeStream() {
    if (eventSource) { eventSource.close(); eventSource = null; }
  }

  function renderArtifacts(artifacts) {
    const box = el("m-artifacts");
    box.innerHTML = "";
    for (const art of artifacts) {
      const a = document.createElement("a");
      a.className = "btn btn-success btn-block";
      a.href = `${API}/download/${art.file_id}`;
      a.innerHTML = `${icon("download", 16)} Download ${escapeHtml(art.filename)} (${fmtSize(art.size)})`;
      a.setAttribute("download", art.filename);
      box.appendChild(a);
    }
  }

  // ---------------------------------------------------------------- re-attach
  // Re-open a modal for an existing execution and replay/live-tail its stream.
  function openExecution(execId, actionId, fallbackTitle) {
    const a = actions.find((x) => x.id === actionId);
    if (a) {
      openModal(a);           // rebuilds the form; currentExecId reset to null
    } else {
      current = null;
      currentExecId = null;
      closeStream();
      const iconBox = el("m-icon");
      iconBox.className = "card-icon";
      iconBox.innerHTML = icon("activity", 24);
      el("m-title").textContent = fallbackTitle || "Execution";
      el("m-desc").textContent = "";
      el("m-form").innerHTML = `<div class="muted small">This action is no longer available.</div>`;
      setStatus("PENDING");
      modal.classList.add("open");
    }
    el("m-run").classList.remove("hidden");
    el("m-terminal").innerHTML = "";
    el("m-artifacts").innerHTML = "";
    // Opened from the history drawer: dock beside the menu instead of dimming
    // the whole page, so both stay visible.
    if (drawerOpen()) {
      modal.classList.add("docked");
      el("drawer-overlay").classList.remove("open");   // undim behind the drawer
    }
    stream(execId);           // replays buffered output, then live-tails
  }

  async function stopExecution(id) {
    if (!id) return;
    try {
      await fetch(`${API}/executions/${id}/stop`, { method: "POST" });
    } catch (_) { /* stop is best-effort; the status event reflects the result */ }
    refreshHistory();
  }

  // ---------------------------------------------------------------- history
  const drawerOpen = () => el("history-drawer").classList.contains("open");

  function toggleDrawer() {
    const open = el("history-drawer").classList.toggle("open");
    el("drawer-overlay").classList.toggle("open", open);
    if (open) { refreshHistory(); startHistoryPoll(); }
    else stopHistoryPoll();
  }
  function closeDrawer() {
    el("history-drawer").classList.remove("open");
    el("drawer-overlay").classList.remove("open");
    stopHistoryPoll();
  }
  function startHistoryPoll() {
    stopHistoryPoll();
    historyTimer = setInterval(refreshHistory, 3000);
  }
  function stopHistoryPoll() {
    if (historyTimer) { clearInterval(historyTimer); historyTimer = null; }
  }

  async function refreshHistory() {
    if (!drawerOpen()) return;
    try {
      const res = await fetch(`${API}/executions?limit=${historyLimit}`);
      if (!res.ok) throw new Error();
      renderHistory(await res.json());
    } catch (_) {
      const list = el("history-list");
      if (!list.children.length) list.innerHTML = `<div class="empty">Failed to load history.</div>`;
    }
  }

  function renderHistory(items) {
    const list = el("history-list");
    if (!items.length) { list.innerHTML = `<div class="empty">No executions yet.</div>`; return; }
    list.innerHTML = "";
    for (const it of items) list.appendChild(historyItemEl(it));
  }

  function historyItemEl(it) {
    const st = String(it.status || "PENDING").toUpperCase();
    const item = document.createElement("div");
    item.className = "history-item";

    const main = document.createElement("div");
    main.className = "history-item-main";
    main.innerHTML =
      `<div class="history-item-title">${escapeHtml(it.action_title || "Action")}</div>` +
      `<div class="muted small">${escapeHtml(relTime(it.finished_at || it.created_at))}</div>`;
    main.addEventListener("click", () => openExecution(it.id, it.action_id, it.action_title));
    item.appendChild(main);

    const badge = document.createElement("span");
    badge.className = "badge badge-" + st.toLowerCase();
    badge.textContent = st.charAt(0) + st.slice(1).toLowerCase();
    item.appendChild(badge);

    if (st === "RUNNING" || st === "PENDING") {
      const stop = document.createElement("button");
      stop.className = "btn btn-danger btn-sm";
      stop.textContent = "Stop";
      stop.addEventListener("click", (e) => { e.stopPropagation(); stopExecution(it.id); });
      item.appendChild(stop);
    }
    return item;
  }

  function relTime(iso) {
    if (!iso) return "";
    const t = new Date(iso).getTime();
    if (Number.isNaN(t)) return "";
    let s = Math.round((Date.now() - t) / 1000);
    if (s < 0) s = 0;
    if (s < 60) return s + "s ago";
    const m = Math.floor(s / 60);
    if (m < 60) return m + "m ago";
    const h = Math.floor(m / 60);
    if (h < 24) return h + "h ago";
    return Math.floor(h / 24) + "d ago";
  }

  // ---------------------------------------------------------------- helpers
  function setStatus(state) {
    const map = {
      PENDING: ["badge-pending", "Pending"],
      RUNNING: ["badge-running", "Running"],
      SUCCESS: ["badge-success", "Success"],
      FAILED: ["badge-failed", "Failed"],
      STOPPED: ["badge-stopped", "Stopped"],
    };
    const [cls, text] = map[state] || map.PENDING;
    const badge = el("m-status");
    badge.className = "badge " + cls;
    badge.textContent = text;
    badge.dataset.state = state;

    // While an execution is active and in flight, offer Stop instead of Execute.
    const active = !!currentExecId && (state === "RUNNING" || state === "PENDING");
    el("m-stop").classList.toggle("hidden", !active);
    el("m-execute").classList.toggle("hidden", active);
  }

  function appendLine(text, kind) {
    const term = el("m-terminal");
    const line = document.createElement("div");
    if (kind) line.className = kind;
    line.textContent = text;
    term.appendChild(line);
    term.scrollTop = term.scrollHeight;
  }

  function fmtSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / 1048576).toFixed(1) + " MB";
  }

  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  const escapeAttr = escapeHtml;
  const truthy = (v) => v === true || ["1", "true", "yes", "on"].includes(String(v).trim().toLowerCase());

  // FastAPI errors: detail is a string (HTTPException) or a list of {loc,msg}
  // objects (422 validation). Render either as readable text.
  function errText(body, fallback) {
    const d = body && body.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      return d.map((e) => {
        const loc = Array.isArray(e.loc) ? e.loc.filter((x) => x !== "body").join(".") : "";
        return (loc ? loc + ": " : "") + (e.msg || JSON.stringify(e));
      }).join("; ");
    }
    if (d && typeof d === "object") return d.msg || JSON.stringify(d);
    return fallback || "Request failed";
  }
  async function readErr(res, fallback) {
    const body = await res.json().catch(() => ({}));
    return errText(body, fallback || res.statusText);
  }

  // ---------------------------------------------------------------- events
  search.addEventListener("input", render);
  el("m-execute").addEventListener("click", execute);
  el("m-stop").addEventListener("click", () => stopExecution(currentExecId));
  el("history-toggle").innerHTML = icon("activity", 18);
  el("history-toggle").addEventListener("click", toggleDrawer);
  el("history-close").addEventListener("click", closeDrawer);
  el("drawer-overlay").addEventListener("click", closeDrawer);
  document.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", closeModal));
  modal.addEventListener("click", (e) => {
    // A docked (history) modal recenters and closes the menu on any click.
    if (modal.classList.contains("docked")) {
      modal.classList.remove("docked");
      closeDrawer();
      return;
    }
    if (e.target === modal) closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (modal.classList.contains("open")) closeModal();
    else if (drawerOpen()) closeDrawer();
  });

  load();
})();
