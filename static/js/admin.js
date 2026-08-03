/* OpsPulse admin builder: login, tag bank, action/param editor with icon
 * picker and multi-tag selection. */
(() => {
  "use strict";

  const API = "/api/v1";
  const el = (id) => document.getElementById(id);
  const icon = (key, size) => (window.OpsIcons ? window.OpsIcons.render(key, size) : "");
  const tagClass = (c) => "tag-" + (c || "slate");

  let actions = [];
  let tags = [];
  let availableScripts = [];
  let selectedIcon = "box";
  let selectedFunc = null;    // chosen function tag id (or null)
  let selectedTeam = null;    // chosen team tag id (or null)
  let tagColorChoice = "teal";
  let tagTypeChoice = "function";

  const isTeam = (t) => t && t.type === "team";
  const funcTags = () => tags.filter((t) => t.type !== "team");
  const teamTags = () => tags.filter((t) => t.type === "team");

  const PARAM_TYPES = ["text", "number", "checkbox", "radio", "select", "dynamic_select"];
  const TAG_COLORS = ["teal", "sage", "green", "blue", "indigo", "cyan", "plum", "rose", "clay", "amber", "slate"];

  // ------------------------------------------------------------- auth
  async function checkSession() {
    const res = await fetch(`${API}/admin/session`);
    const { authenticated } = await res.json();
    authenticated ? showBuilder() : showLogin();
  }
  function showLogin() {
    el("login-view").classList.remove("hidden");
    el("builder-view").classList.add("hidden");
    el("logout").classList.add("hidden");
  }
  async function showBuilder() {
    el("login-view").classList.add("hidden");
    el("builder-view").classList.remove("hidden");
    el("logout").classList.remove("hidden");
    await Promise.all([loadActions(), loadTags(), loadScripts()]);
  }
  async function login() {
    const res = await fetch(`${API}/admin/login`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: el("password").value }),
    });
    if (res.ok) { el("password").value = ""; showBuilder(); }
    else toast("Invalid password", "error");
  }
  async function logout() { await fetch(`${API}/admin/logout`, { method: "POST" }); showLogin(); }

  // ------------------------------------------------------------- data
  async function loadActions() {
    actions = await (await fetch(`${API}/actions`)).json();
    renderActionList();
  }
  async function loadTags() {
    tags = await (await fetch(`${API}/tags`)).json();
    renderTagList();
  }
  async function loadScripts() {
    try {
      const res = await fetch(`${API}/admin/scripts`);
      if (!res.ok) return;
      availableScripts = (await res.json()).scripts || [];
    } catch (_) {}
  }
  const tagById = (id) => tags.find((t) => t.id === id);

  // Populate the script <select>, keeping the action's current value even if
  // it isn't in the discovered list.
  function fillScriptSelect(current) {
    const sel = el("e-script");
    const opts = [...availableScripts];
    if (current && !opts.includes(current)) opts.unshift(current);
    sel.innerHTML = `<option value="">— select a script —</option>` +
      opts.map((s) => `<option value="${escapeAttr(s)}">${escapeHtml(s)}</option>`).join("");
    sel.value = current || "";
  }

  function tagChip(t) {
    return isTeam(t)
      ? `<span class="team-badge">${escapeHtml(t.name)}</span>`
      : `<span class="tag-pill ${tagClass(t.color)}">${escapeHtml(t.name)}</span>`;
  }

  // ------------------------------------------------------------- tag bank
  function renderTagList() {
    const list = el("tag-list");
    if (!tags.length) {
      list.innerHTML = `<div class="muted small">No tags yet. Create one to color and group your actions.</div>`;
      return;
    }
    list.innerHTML = "";
    for (const t of tags) {
      const row = document.createElement("div");
      row.className = "tag-row between";
      row.style.padding = "6px 0";
      row.innerHTML = `
        <div class="flex">${tagChip(t)}<span class="muted small">${isTeam(t) ? "team" : "function"}</span></div>
        <button class="btn btn-ghost btn-sm">Edit</button>`;
      row.querySelector("button").addEventListener("click", () => openTagEditor(t));
      list.appendChild(row);
    }
  }

  function openTagEditor(tag) {
    const isNew = !tag;
    el("tag-editor-title").textContent = isNew ? "New Tag" : "Edit Tag";
    el("t-id").value = isNew ? "" : tag.id;
    el("t-name").value = isNew ? "" : tag.name;
    tagColorChoice = isNew ? "teal" : (tag.color || "teal");
    tagTypeChoice = isNew ? "function" : (tag.type || "function");
    el("t-type").value = tagTypeChoice;
    el("delete-tag").classList.toggle("hidden", isNew);
    syncTagType();
    renderSwatches();
    renderTagPreview();
    el("tag-editor").classList.add("open");
  }
  function closeTagEditor() { el("tag-editor").classList.remove("open"); }

  function syncTagType() {
    tagTypeChoice = el("t-type").value;
    // Team tags are colorless — hide the color picker.
    el("t-color-field").classList.toggle("hidden", tagTypeChoice === "team");
    renderTagPreview();
  }

  function renderSwatches() {
    const box = el("t-swatches");
    box.innerHTML = "";
    for (const c of TAG_COLORS) {
      const s = document.createElement("div");
      s.className = "swatch " + tagClass(c) + (c === tagColorChoice ? " selected" : "");
      s.title = c;
      s.addEventListener("click", () => { tagColorChoice = c; renderSwatches(); renderTagPreview(); });
      box.appendChild(s);
    }
  }
  function renderTagPreview() {
    const name = el("t-name").value.trim() || "tag name";
    el("t-preview").innerHTML = tagTypeChoice === "team"
      ? `<span class="team-badge">${escapeHtml(name)}</span>`
      : `<span class="tag-pill ${tagClass(tagColorChoice)}">${escapeHtml(name)}</span>`;
  }

  async function saveTag() {
    const id = el("t-id").value;
    const name = el("t-name").value.trim();
    if (!name) return toast("Tag name is required", "error");
    const payload = { name, color: tagColorChoice, type: tagTypeChoice };
    const url = id ? `${API}/tags/${id}` : `${API}/tags`;
    const res = await fetch(url, {
      method: id ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    if (res.ok) { closeTagEditor(); await loadTags(); toast("Tag saved", "success"); }
    else toast(await readErr(res, "Save failed"), "error");
  }
  async function deleteTag() {
    const id = el("t-id").value;
    if (!id || !confirm("Delete this tag? It will be removed from any actions using it.")) return;
    const res = await fetch(`${API}/tags/${id}`, { method: "DELETE" });
    if (res.ok || res.status === 204) {
      closeTagEditor(); await Promise.all([loadTags(), loadActions()]); toast("Tag deleted", "success");
    } else toast("Delete failed", "error");
  }

  // ------------------------------------------------------------- action list
  function renderActionList() {
    const list = el("action-list");
    if (!actions.length) {
      list.innerHTML = `<div class="empty">No actions yet. Click "New Action".</div>`;
      return;
    }
    list.innerHTML = "";
    for (const a of actions) {
      const details = a.tag_details || [];
      const team = details.find((t) => t.type === "team");
      const func = details.find((t) => t.type !== "team");
      const chips = [
        func ? `<span class="tag-pill ${tagClass(func.color)}">${escapeHtml(func.name)}</span>` : "",
        team ? `<span class="team-badge">${escapeHtml(team.name)}</span>` : "",
      ].join("");
      const card = document.createElement("div");
      card.className = "param-card";
      card.innerHTML = `<div class="between">
        <div class="flex">
          <span class="card-icon">${icon(a.icon, 20)}</span>
          <div>
            <div style="font-weight:650;">${escapeHtml(a.title)}</div>
            <div class="muted small mono">${escapeHtml(a.script_path)}</div>
          </div>
        </div>
        <button class="btn btn-ghost btn-sm">Edit</button>
      </div>
      ${chips ? `<div class="card-tags" style="margin-top:10px;align-items:center;">${chips}</div>` : ""}`;
      card.querySelector("button").addEventListener("click", () => openEditor(a));
      list.appendChild(card);
    }
  }

  // ------------------------------------------------------------- action editor
  function openEditor(action) {
    const isNew = !action;
    el("editor-title").textContent = isNew ? "New Action" : "Edit Action";
    el("e-id").value = isNew ? "" : action.id;
    el("e-title").value = isNew ? "" : action.title || "";
    el("e-description").value = isNew ? "" : action.description || "";
    fillScriptSelect(isNew ? "" : action.script_path || "");
    el("e-interpreter").value = isNew ? "auto" : action.interpreter || "auto";
    el("e-output").value = isNew ? "" : action.output_subdir || "";
    el("delete-action").classList.toggle("hidden", isNew);

    selectedIcon = isNew ? "rocket" : (window.OpsIcons && window.OpsIcons.has(action.icon) ? action.icon : "box");
    const details = isNew ? [] : (action.tag_details || []);
    selectedFunc = (details.find((t) => t.type !== "team") || {}).id || null;
    selectedTeam = (details.find((t) => t.type === "team") || {}).id || null;
    renderIconPicker();
    renderTagSelect();

    el("params").innerHTML = "";
    if (!isNew) (action.parameters || []).forEach(addParamRow);
    el("editor").classList.add("open");
  }
  function closeEditor() { el("editor").classList.remove("open"); }

  function renderIconPicker() {
    const grid = el("e-icons");
    grid.innerHTML = "";
    for (const key of (window.OpsIcons ? window.OpsIcons.ICON_KEYS : [])) {
      const cell = document.createElement("div");
      cell.className = "icon-cell" + (key === selectedIcon ? " selected" : "");
      cell.title = key;
      cell.innerHTML = icon(key, 20);
      cell.addEventListener("click", () => { selectedIcon = key; renderIconPicker(); });
      grid.appendChild(cell);
    }
  }

  function renderTagSelect() {
    renderTagGroup(el("e-func-tags"), funcTags(), () => selectedFunc,
      (id) => { selectedFunc = id; }, "No function tags yet.");
    renderTagGroup(el("e-team-tags"), teamTags(), () => selectedTeam,
      (id) => { selectedTeam = id; }, "No teams yet.");
  }

  // Single-select group: clicking the chosen chip deselects it.
  function renderTagGroup(box, list, getSel, setSel, emptyMsg) {
    box.innerHTML = "";
    if (!list.length) { box.innerHTML = `<div class="muted small">${emptyMsg}</div>`; return; }
    for (const t of list) {
      const chosen = getSel() === t.id;
      const choice = document.createElement("div");
      choice.className = "tag-choice" + (chosen ? " selected" : "");
      choice.innerHTML = tagChip(t);
      choice.addEventListener("click", () => {
        setSel(chosen ? null : t.id);
        renderTagSelect();
      });
      box.appendChild(choice);
    }
  }

  function addParamRow(p = {}) {
    const row = document.createElement("div");
    row.className = "param-card";
    row.innerHTML = `
      <div class="between">
        <strong class="small">Parameter</strong>
        <button class="btn btn-ghost btn-sm" data-remove>Remove</button>
      </div>
      <div class="row">
        <div class="field"><label>Name (var) <span class="req">*</span></label>
          <input class="p-name" type="text" placeholder="branch" value="${escapeAttr(p.name || "")}" /></div>
        <div class="field"><label>Label</label>
          <input class="p-label" type="text" placeholder="Branch" value="${escapeAttr(p.label || "")}" /></div>
        <div class="field" style="max-width:170px;"><label>Type</label>
          <select class="p-type">${PARAM_TYPES.map((t) =>
            `<option ${p.type === t ? "selected" : ""}>${t}</option>`).join("")}</select></div>
      </div>
      <div class="row">
        <div class="check-row"><input class="p-required" type="checkbox" ${p.required ? "checked" : ""}/>
          <label style="margin:0;">Required</label></div>
        <div class="field"><label>Default</label>
          <input class="p-default" type="text" value="${escapeAttr(p.default ?? "")}" /></div>
      </div>
      <div class="field p-static hidden"><label>Options (comma-separated)</label>
        <input class="p-options" type="text" placeholder="dev, staging, prod"
          value="${escapeAttr((p.options || []).join(", "))}" />
        <div class="hint p-cbhint hidden">A checkbox with options becomes a multi-select group.
          Leave empty for a single on/off flag. Default(s) may be comma-separated.</div></div>
      <div class="p-dynamic hidden">
        <div class="field"><label>Endpoint (URL)</label>
          <input class="p-endpoint" type="text" placeholder="\${GITLAB_API_URL}/projects/42/repository/branches"
            value="${escapeAttr(p.endpoint || "")}" /></div>
        <div class="row">
          <div class="field"><label>Response key</label>
            <input class="p-respkey" type="text" placeholder="[].name"
              value="${escapeAttr(p.response_key || "")}" /></div>
          <div class="field"><label>Auth header (secret)</label>
            <input class="p-auth" type="text" placeholder="PRIVATE-TOKEN: \${GITLAB_TOKEN}"
              value="${escapeAttr(p.auth_header || "")}" /></div>
        </div>
        <div class="hint">Endpoint and Auth header may use <span class="mono">\${GITLAB_API_URL}</span> /
          <span class="mono">\${GITLAB_TOKEN}</span> / <span class="mono">\${OPENSHIFT_API_URL}</span> /
          <span class="mono">\${OPENSHIFT_TOKEN}</span> — injected server-side, never sent to the browser.
          Response key parses the JSON, e.g. <span class="mono">[].name</span> or
          <span class="mono">items[].metadata.name</span>.</div>
        <div class="between" style="margin-top:10px;">
          <button type="button" class="btn btn-ghost btn-sm" data-test-dd>▶ Test dropdown</button>
          <span class="dd-result small muted"></span>
        </div>
      </div>`;

    const typeSel = row.querySelector(".p-type");
    const sync = () => {
      const t = typeSel.value;
      const hasOptions = t === "select" || t === "radio" || t === "checkbox";
      row.querySelector(".p-static").classList.toggle("hidden", !hasOptions);
      row.querySelector(".p-cbhint").classList.toggle("hidden", t !== "checkbox");
      row.querySelector(".p-dynamic").classList.toggle("hidden", t !== "dynamic_select");
    };
    typeSel.addEventListener("change", sync);
    sync();
    row.querySelector("[data-test-dd]").addEventListener("click", () => testDropdown(row));
    row.querySelector("[data-remove]").addEventListener("click", () => row.remove());
    el("params").appendChild(row);
  }

  function collectParams() {
    const params = [];
    for (const row of el("params").children) {
      const name = row.querySelector(".p-name").value.trim();
      if (!name) continue;
      const type = row.querySelector(".p-type").value;
      const defaultRaw = row.querySelector(".p-default").value;
      const p = {
        name, label: row.querySelector(".p-label").value.trim(), type,
        required: row.querySelector(".p-required").checked,
        default: defaultRaw === "" ? null : defaultRaw, options: [],
      };
      if (type === "select" || type === "radio" || type === "checkbox") {
        p.options = row.querySelector(".p-options").value.split(",").map((s) => s.trim()).filter(Boolean);
      }
      if (type === "dynamic_select") {
        p.endpoint = row.querySelector(".p-endpoint").value.trim() || null;
        p.response_key = row.querySelector(".p-respkey").value.trim() || null;
        p.auth_header = row.querySelector(".p-auth").value.trim() || null;
      }
      params.push(p);
    }
    return params;
  }

  async function testDropdown(row) {
    const out = row.querySelector(".dd-result");
    const cfg = {
      endpoint: row.querySelector(".p-endpoint").value.trim() || null,
      response_key: row.querySelector(".p-respkey").value.trim() || null,
      auth_header: row.querySelector(".p-auth").value.trim() || null,
    };
    out.textContent = "Testing…";
    out.className = "dd-result small muted";
    try {
      const res = await fetch(`${API}/dynamic-options/test`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cfg),
      });
      if (!res.ok) {
        out.textContent = "✗ " + (await readErr(res, "Test failed"));
        out.className = "dd-result small err-text";
        return;
      }
      const d = await res.json();
      const sample = d.options.slice(0, 8).map((o) => o.label).join(", ");
      out.textContent = `✓ ${d.count} option(s)` +
        (sample ? ": " + sample + (d.count > 8 ? " …" : "") : "");
      out.className = "dd-result small ok-text";
    } catch (e) {
      out.textContent = "✗ " + e.message;
      out.className = "dd-result small err-text";
    }
  }

  function validateParams(params) {
    for (const p of params) {
      const hasDefault = p.default !== null && p.default !== undefined && String(p.default).trim() !== "";
      if (p.type === "number" && hasDefault) {
        const n = Number(p.default);
        if (Number.isNaN(n)) return `Parameter "${p.name}": default must be a number`;
        if (n < 0) return `Parameter "${p.name}": default must be 0 or greater`;
      }
      if ((p.type === "select" || p.type === "radio") && hasDefault) {
        if (p.options.length && !p.options.includes(String(p.default)))
          return `Parameter "${p.name}": default "${p.default}" is not in the options list`;
      }
      if (p.type === "checkbox" && p.options.length && hasDefault) {
        const bad = String(p.default).split(",").map((s) => s.trim()).filter(Boolean)
          .filter((x) => !p.options.includes(x));
        if (bad.length) return `Parameter "${p.name}": default(s) ${bad.join(", ")} not in the options list`;
      }
    }
    return null;
  }

  async function saveAction() {
    const id = el("e-id").value;
    const payload = {
      title: el("e-title").value.trim(),
      description: el("e-description").value.trim(),
      icon: selectedIcon,
      tags: [selectedFunc, selectedTeam].filter(Boolean),
      script_path: el("e-script").value.trim(),
      interpreter: el("e-interpreter").value,
      output_subdir: el("e-output").value.trim(),
      parameters: collectParams(),
    };
    if (!payload.title) return toast("Title is required", "error");
    if (!payload.script_path) return toast("Script path is required", "error");
    const perr = validateParams(payload.parameters);
    if (perr) return toast(perr, "error");

    const url = id ? `${API}/actions/${id}` : `${API}/actions`;
    const res = await fetch(url, {
      method: id ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    if (res.ok) { closeEditor(); await loadActions(); toast("Action saved", "success"); }
    else toast(await readErr(res, "Save failed"), "error");
  }

  async function deleteAction() {
    const id = el("e-id").value;
    if (!id || !confirm("Delete this action?")) return;
    const res = await fetch(`${API}/actions/${id}`, { method: "DELETE" });
    if (res.ok || res.status === 204) { closeEditor(); await loadActions(); toast("Action deleted", "success"); }
    else toast("Delete failed", "error");
  }

  // ------------------------------------------------------------- helpers
  let toastTimer = null;
  function toast(msg, kind) {
    const t = el("toast");
    t.textContent = msg;
    t.className = "toast show" + (kind ? " " + kind : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (t.className = "toast"), 3000);
  }
  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  const escapeAttr = escapeHtml;

  // FastAPI errors: detail is a string (HTTPException) or a list of
  // {loc, msg} objects (422 validation). Render either as readable text.
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

  // ------------------------------------------------------------- events
  el("login-btn").addEventListener("click", login);
  el("password").addEventListener("keydown", (e) => { if (e.key === "Enter") login(); });
  el("logout").addEventListener("click", logout);
  el("new-action").addEventListener("click", () => openEditor(null));
  el("add-param").addEventListener("click", () => addParamRow());
  el("save-action").addEventListener("click", saveAction);
  el("delete-action").addEventListener("click", deleteAction);
  el("new-tag").addEventListener("click", () => openTagEditor(null));
  el("save-tag").addEventListener("click", saveTag);
  el("delete-tag").addEventListener("click", deleteTag);
  el("t-name").addEventListener("input", renderTagPreview);
  el("t-type").addEventListener("change", syncTagType);
  el("jump-new-tag").addEventListener("click", (e) => { e.preventDefault(); closeEditor(); openTagEditor(null); });
  document.querySelectorAll("[data-close-editor]").forEach((b) => b.addEventListener("click", closeEditor));
  document.querySelectorAll("[data-close-tag]").forEach((b) => b.addEventListener("click", closeTagEditor));

  checkSession();
})();
