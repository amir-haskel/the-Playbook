/* OpsPulse admin builder: login, action list, action/param editor. */
(() => {
  "use strict";

  const API = "/api/v1";
  const el = (id) => document.getElementById(id);
  let actions = [];
  let availableScripts = [];

  const PARAM_TYPES = ["text", "number", "checkbox", "radio", "select", "dynamic_select"];
  const DYNAMIC_TYPES = ["gitlab-branches", "oc-namespaces", "custom"];

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
    await Promise.all([loadActions(), loadScripts()]);
  }

  async function login() {
    const res = await fetch(`${API}/admin/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: el("password").value }),
    });
    if (res.ok) { el("password").value = ""; showBuilder(); }
    else toast("Invalid password", "error");
  }

  async function logout() {
    await fetch(`${API}/admin/logout`, { method: "POST" });
    showLogin();
  }

  // ------------------------------------------------------------- data
  async function loadActions() {
    const res = await fetch(`${API}/actions`);
    actions = await res.json();
    renderList();
  }

  async function loadScripts() {
    try {
      const res = await fetch(`${API}/admin/scripts`);
      if (!res.ok) return;
      availableScripts = (await res.json()).scripts || [];
      el("scripts-list").innerHTML =
        availableScripts.map((s) => `<option value="${escapeAttr(s)}"></option>`).join("");
    } catch (_) { /* non-fatal */ }
  }

  function renderList() {
    const list = el("action-list");
    if (!actions.length) {
      list.innerHTML = `<div class="empty">No actions yet. Click “New Action”.</div>`;
      return;
    }
    list.innerHTML = "";
    for (const a of actions) {
      const card = document.createElement("div");
      card.className = "param-card";
      card.innerHTML = `<div class="between">
        <div class="flex">
          <span class="card-icon">${escapeHtml(a.icon || "▶️")}</span>
          <div>
            <div style="font-weight:700;">${escapeHtml(a.title)}</div>
            <div class="muted small mono">${escapeHtml(a.script_path)} · ${escapeHtml(a.category)} · ${(a.parameters||[]).length} param(s)</div>
          </div>
        </div>
        <button class="btn btn-ghost btn-sm">Edit</button>
      </div>`;
      card.querySelector("button").addEventListener("click", () => openEditor(a));
      list.appendChild(card);
    }
  }

  // ------------------------------------------------------------- editor
  function openEditor(action) {
    const isNew = !action;
    el("editor-title").textContent = isNew ? "New Action" : "Edit Action";
    el("e-id").value = isNew ? "" : action.id;
    el("e-title").value = isNew ? "" : action.title || "";
    el("e-icon").value = isNew ? "" : action.icon || "";
    el("e-description").value = isNew ? "" : action.description || "";
    el("e-category").value = isNew ? "General" : action.category || "General";
    el("e-color").value = isNew ? "indigo" : action.color || "indigo";
    el("e-script").value = isNew ? "" : action.script_path || "";
    el("e-interpreter").value = isNew ? "auto" : action.interpreter || "auto";
    el("e-output").value = isNew ? "" : action.output_subdir || "";
    el("delete-action").classList.toggle("hidden", isNew);

    el("params").innerHTML = "";
    if (!isNew) (action.parameters || []).forEach(addParamRow);

    el("editor").classList.add("open");
  }

  function closeEditor() { el("editor").classList.remove("open"); }

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
      <div class="field p-static hidden"><label>Static options (comma-separated)</label>
        <input class="p-options" type="text" placeholder="dev, staging, prod"
          value="${escapeAttr((p.options || []).join(", "))}" /></div>
      <div class="p-dynamic hidden">
        <div class="row">
          <div class="field" style="max-width:210px;"><label>Dynamic source</label>
            <select class="p-dyntype">${DYNAMIC_TYPES.map((t) =>
              `<option ${p.dynamic_type === t ? "selected" : ""}>${t}</option>`).join("")}</select></div>
          <div class="field"><label>Endpoint (path or URL)</label>
            <input class="p-endpoint" type="text" placeholder="projects/42/repository/branches"
              value="${escapeAttr(p.endpoint || "")}" /></div>
        </div>
        <div class="row">
          <div class="field"><label>Response key</label>
            <input class="p-respkey" type="text" placeholder="[].name"
              value="${escapeAttr(p.response_key || "")}" /></div>
          <div class="field"><label>Auth header (secret)</label>
            <input class="p-auth" type="text" placeholder="PRIVATE-TOKEN: \${GITLAB_TOKEN}"
              value="${escapeAttr(p.auth_header || "")}" /></div>
        </div>
        <div class="hint">Use <span class="mono">\${GITLAB_TOKEN}</span> / <span class="mono">\${OPENSHIFT_TOKEN}</span>
          — secrets are injected server-side and never sent to the browser. Built-in sources prefill the rest.</div>
      </div>`;

    const typeSel = row.querySelector(".p-type");
    const sync = () => {
      const t = typeSel.value;
      row.querySelector(".p-static").classList.toggle("hidden", !(t === "select" || t === "radio"));
      row.querySelector(".p-dynamic").classList.toggle("hidden", t !== "dynamic_select");
    };
    typeSel.addEventListener("change", sync);
    sync();
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
        name,
        label: row.querySelector(".p-label").value.trim(),
        type,
        required: row.querySelector(".p-required").checked,
        default: defaultRaw === "" ? null : defaultRaw,
        options: [],
      };
      if (type === "select" || type === "radio") {
        p.options = row.querySelector(".p-options").value
          .split(",").map((s) => s.trim()).filter(Boolean);
      }
      if (type === "dynamic_select") {
        p.dynamic_type = row.querySelector(".p-dyntype").value;
        p.endpoint = row.querySelector(".p-endpoint").value.trim() || null;
        p.response_key = row.querySelector(".p-respkey").value.trim() || null;
        p.auth_header = row.querySelector(".p-auth").value.trim() || null;
      }
      params.push(p);
    }
    return params;
  }

  async function saveAction() {
    const id = el("e-id").value;
    const payload = {
      title: el("e-title").value.trim(),
      description: el("e-description").value.trim(),
      icon: el("e-icon").value.trim(),
      color: el("e-color").value,
      category: el("e-category").value.trim() || "General",
      script_path: el("e-script").value.trim(),
      interpreter: el("e-interpreter").value,
      output_subdir: el("e-output").value.trim(),
      parameters: collectParams(),
    };
    if (!payload.title) return toast("Title is required", "error");
    if (!payload.script_path) return toast("Script path is required", "error");

    const url = id ? `${API}/actions/${id}` : `${API}/actions`;
    const method = id ? "PUT" : "POST";
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      closeEditor();
      await loadActions();
      toast("Action saved", "success");
    } else {
      const body = await res.json().catch(() => ({}));
      toast(body.detail || "Save failed", "error");
    }
  }

  async function deleteAction() {
    const id = el("e-id").value;
    if (!id) return;
    if (!confirm("Delete this action?")) return;
    const res = await fetch(`${API}/actions/${id}`, { method: "DELETE" });
    if (res.ok || res.status === 204) {
      closeEditor();
      await loadActions();
      toast("Action deleted", "success");
    } else {
      toast("Delete failed", "error");
    }
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

  // ------------------------------------------------------------- events
  el("login-btn").addEventListener("click", login);
  el("password").addEventListener("keydown", (e) => { if (e.key === "Enter") login(); });
  el("logout").addEventListener("click", logout);
  el("new-action").addEventListener("click", () => openEditor(null));
  el("add-param").addEventListener("click", () => addParamRow());
  el("save-action").addEventListener("click", saveAction);
  el("delete-action").addEventListener("click", deleteAction);
  document.querySelectorAll("[data-close-editor]").forEach((b) =>
    b.addEventListener("click", closeEditor));

  checkSession();
})();
