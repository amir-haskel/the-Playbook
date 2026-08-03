/* OpsPulse dashboard: card grid, search, execution modal, SSE streaming. */
(() => {
  "use strict";

  const API = "/api/v1";
  let actions = [];
  let current = null;          // action open in the modal
  let eventSource = null;

  const el = (id) => document.getElementById(id);
  const board = el("board");
  const search = el("search");
  const modal = el("modal");

  const COLORS = new Set([
    "slate", "indigo", "blue", "green", "red", "amber", "purple", "cyan", "pink",
  ]);
  const accent = (c) => "accent-" + (COLORS.has(c) ? c : "indigo");

  // ---------------------------------------------------------------- load
  async function load() {
    try {
      const res = await fetch(`${API}/actions`);
      actions = await res.json();
      render();
    } catch (e) {
      board.innerHTML = `<div class="empty">Failed to load actions.</div>`;
    }
  }

  function render() {
    const q = search.value.trim().toLowerCase();
    const filtered = actions.filter((a) => {
      if (!q) return true;
      return (
        (a.title || "").toLowerCase().includes(q) ||
        (a.description || "").toLowerCase().includes(q) ||
        (a.category || "").toLowerCase().includes(q)
      );
    });

    if (!filtered.length) {
      board.innerHTML = `<div class="empty">${
        actions.length ? "No actions match your search." :
        "No actions configured yet. Head to <a href='/admin'>Admin</a> to create one."
      }</div>`;
      return;
    }

    // Group by category.
    const groups = {};
    for (const a of filtered) (groups[a.category || "General"] ||= []).push(a);

    board.innerHTML = "";
    for (const cat of Object.keys(groups).sort()) {
      const title = document.createElement("div");
      title.className = "section-title";
      title.textContent = cat;
      board.appendChild(title);

      const grid = document.createElement("div");
      grid.className = "grid";
      for (const a of groups[cat]) grid.appendChild(cardEl(a));
      board.appendChild(grid);
    }
  }

  function cardEl(a) {
    const card = document.createElement("div");
    card.className = "card " + accent(a.color);
    card.innerHTML = `
      <div class="card-icon">${escapeHtml(a.icon || "▶️")}</div>
      <div class="card-title">${escapeHtml(a.title)}</div>
      <div class="card-desc">${escapeHtml(a.description || "")}</div>
      <span class="card-tag">${escapeHtml(a.category || "General")}</span>`;
    card.addEventListener("click", () => openModal(a));
    return card;
  }

  // ---------------------------------------------------------------- modal
  function openModal(a) {
    current = a;
    closeStream();
    el("m-icon").textContent = a.icon || "▶️";
    el("m-title").textContent = a.title;
    el("m-desc").textContent = a.description || "";
    el("m-run").classList.add("hidden");
    el("m-terminal").innerHTML = "";
    el("m-artifacts").innerHTML = "";
    setStatus("PENDING");
    buildForm(a);
    const btn = el("m-execute");
    btn.disabled = false;
    btn.textContent = "▶ Execute";
    modal.classList.add("open");
  }

  function closeModal() {
    modal.classList.remove("open");
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
  }

  function fieldEl(action, p) {
    const wrap = document.createElement("div");
    wrap.className = "field";
    const label = p.label || p.name;
    const req = p.required ? ' <span class="req">*</span>' : "";
    const id = "f_" + p.name;

    if (p.type === "checkbox") {
      wrap.innerHTML = `<div class="check-row">
        <input type="checkbox" id="${id}" data-name="${p.name}" ${p.default ? "checked" : ""}/>
        <label for="${id}" style="margin:0;">${escapeHtml(label)}${req}</label></div>`;
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
      input.id = id; input.dataset.name = p.name;
      if (p.default != null) input.value = p.default;
      wrap.appendChild(input);
    }
    return wrap;
  }

  async function loadDynamic(action, p, sel) {
    try {
      const url = `${API}/dynamic-options/${encodeURIComponent(p.dynamic_type || "custom")}` +
        `?action_id=${encodeURIComponent(action.id)}&param=${encodeURIComponent(p.name)}`;
      const res = await fetch(url);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || res.statusText);
      }
      const opts = await res.json();
      sel.innerHTML = `<option value="">— select —</option>` +
        opts.map((o) => `<option value="${escapeAttr(o.value)}">${escapeHtml(o.label)}</option>`).join("");
      if (p.default) sel.value = p.default;
      if (!opts.length) sel.innerHTML = `<option value="">(no options returned)</option>`;
    } catch (e) {
      sel.innerHTML = `<option value="">⚠ ${escapeHtml(e.message)}</option>`;
    }
  }

  function collectValues() {
    const values = {};
    if (!current.parameters) return values;
    for (const p of current.parameters) {
      if (p.type === "checkbox") {
        values[p.name] = el("f_" + p.name).checked;
      } else if (p.type === "radio") {
        const chosen = document.querySelector(`input[name="f_${p.name}"]:checked`);
        values[p.name] = chosen ? chosen.value : "";
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
      if (!res.ok) throw new Error(body.detail || "Execution failed to start");
      execId = body.execution_id;
    } catch (e) {
      appendLine(e.message, "err");
      setStatus("FAILED");
      btn.disabled = false;
      return;
    }
    stream(execId);
  }

  function stream(execId) {
    closeStream();
    setStatus("RUNNING");
    eventSource = new EventSource(`${API}/stream/${execId}`);

    eventSource.addEventListener("stdout", (e) => appendLine(JSON.parse(e.data).line));
    eventSource.addEventListener("stderr", (e) => appendLine(JSON.parse(e.data).line, "err"));
    eventSource.addEventListener("status", (e) => {
      const data = JSON.parse(e.data);
      setStatus(data.status);
      renderArtifacts(data.artifacts || []);
      closeStream();
      el("m-execute").disabled = false;
    });
    eventSource.onerror = () => {
      // Stream closed (normal on completion) — only surface if still running.
      if (el("m-status").dataset.state === "RUNNING") {
        appendLine("[connection closed]", "sys");
      }
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
      a.textContent = `⬇ Download ${art.filename} (${fmtSize(art.size)})`;
      a.setAttribute("download", art.filename);
      box.appendChild(a);
    }
  }

  // ---------------------------------------------------------------- helpers
  function setStatus(state) {
    const map = {
      PENDING: ["badge-pending", "Pending"],
      RUNNING: ["badge-running", "Running"],
      SUCCESS: ["badge-success", "Success"],
      FAILED: ["badge-failed", "Failed"],
    };
    const [cls, text] = map[state] || map.PENDING;
    const badge = el("m-status");
    badge.className = "badge " + cls;
    badge.textContent = text;
    badge.dataset.state = state;
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

  // ---------------------------------------------------------------- events
  search.addEventListener("input", render);
  el("m-execute").addEventListener("click", execute);
  document.querySelectorAll("[data-close]").forEach((b) =>
    b.addEventListener("click", closeModal));
  modal.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.classList.contains("open")) closeModal();
  });

  load();
})();
