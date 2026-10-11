/* The Playbook dashboard: unified card grid, tag filter chips, execution modal,
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
  const icon = (key, size) => (window.PlaybookIcons ? window.PlaybookIcons.render(key, size) : "");
  const tagClass = (color) => "tag-" + (color || "slate");
  // A checkbox param whose options are fetched from a dynamic source (endpoint /
  // dynamic_type) and rendered as a multi-select checkbox group.
  const isDynamicCheckbox = (p) => p.type === "checkbox" && !!(p.endpoint || p.dynamic_type);
  // Parameter names may contain whitespace (e.g. "Target Namespace"). We render
  // and submit the LITERAL name, but derive a safe token for DOM ids / element
  // `name` attributes (only [A-Za-z0-9_]) so getElementById and selectors work.
  const domKey = (s) => String(s).replace(/[^A-Za-z0-9_]/g, "_");

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
    refreshSuccessCount();
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
    const label = p.name;
    const req = p.required ? ' <span class="req">*</span>' : "";
    const key = domKey(p.name);
    const id = "f_" + key;

    if (p.type === "checkbox") {
      if (isDynamicCheckbox(p)) {
        // Multi-select checkbox group with options fetched live.
        wrap.innerHTML = `<label>${escapeHtml(label)}${req}</label>`;
        const group = document.createElement("div");
        group.className = "checkbox-group";
        group.innerHTML = `<div class="muted small">Loading options…</div>`;
        wrap.appendChild(group);
        loadDynamicCheckboxes(action, p, group);
        return wrap;
      }
      if (p.options && p.options.length) {
        // Multi-select checkbox group. When select_all is enabled it renders as
        // a vertical .checkbox-group (matching the dynamic path) so the leading
        // "Select all" master checkbox and its divider style apply; otherwise it
        // keeps the compact horizontal .radio-row layout.
        const defaults = String(p.default ?? "").split(",").map((s) => s.trim()).filter(Boolean);
        wrap.innerHTML = `<label>${escapeHtml(label)}${req}</label>`;
        const group = document.createElement("div");
        group.className = p.select_all ? "checkbox-group" : "radio-row";
        const boxes = p.options.map((o) =>
          `<label><input type="checkbox" name="cb_${key}" value="${escapeAttr(o)}" ${
            defaults.includes(o) ? "checked" : ""}/> ${escapeHtml(o)}</label>`).join("");
        group.innerHTML = selAllMarkup(p) + boxes;
        wrap.appendChild(group);
        wireSelectAll(group, key);   // no-op when no master checkbox present
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
    // The combobox's labelable control is its visible text input, not the
    // hidden value holder that carries `id`.
    if (p.type === "dynamic_select") wrap.querySelector("label").setAttribute("for", id + "_q");

    if (p.type === "select") {
      const sel = document.createElement("select");
      sel.id = id; sel.dataset.name = p.name;
      sel.innerHTML = `<option value="">— select —</option>` +
        (p.options || []).map((o) => `<option value="${escapeAttr(o)}">${escapeHtml(o)}</option>`).join("");
      if (p.default) sel.value = p.default;
      wrap.appendChild(sel);
    } else if (p.type === "dynamic_select") {
      wrap.appendChild(buildCombobox(action, p, id));
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

  // Searchable combobox for a dynamic_select param. Fetches options exactly like
  // the old loadDynamic() did, but renders a filterable, keyboard-navigable
  // listbox instead of a native <select> so it stays usable with 200+ options.
  // The chosen option VALUE is mirrored into a hidden <input id="f_<key>"> so the
  // generic collectValues()/paramEmpty() paths keep working unchanged and the
  // submit key remains the literal p.name.
  function buildCombobox(action, p, valueId) {
    const box = document.createElement("div");
    box.className = "combobox";
    box.dataset.name = p.name;

    const hidden = document.createElement("input");
    hidden.type = "hidden";
    hidden.id = valueId;                 // value holder read by collectValues()

    const input = document.createElement("input");
    input.type = "text";
    input.className = "combo-input";
    input.id = valueId + "_q";
    input.autocomplete = "off";
    input.disabled = true;
    input.placeholder = "Loading options…";
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");
    const listId = valueId + "_list";
    input.setAttribute("aria-controls", listId);

    const list = document.createElement("ul");
    list.className = "combo-list";
    list.id = listId;
    list.hidden = true;
    list.setAttribute("role", "listbox");

    box.append(hidden, input, list);

    let options = [];       // [{value,label}] full option set
    let filtered = [];      // options currently shown
    let activeIdx = -1;     // highlighted option within `filtered`
    let selLabel = "";      // label of the committed selection

    const isOpen = () => !list.hidden;
    const setExpanded = (v) => input.setAttribute("aria-expanded", v ? "true" : "false");
    const open = () => { if (!isOpen() && !input.disabled) { list.hidden = false; setExpanded(true); } };
    function close() {
      if (!isOpen()) return;
      list.hidden = true; setExpanded(false);
      activeIdx = -1; input.removeAttribute("aria-activedescendant");
    }

    function commit(value, labelText) {
      hidden.value = value;
      selLabel = labelText;
      input.value = labelText;
      close();
      gateExecute();
    }
    const clearSelection = () => { hidden.value = ""; selLabel = ""; };

    function renderList(showAll) {
      const q = showAll ? "" : input.value.trim().toLowerCase();
      filtered = q ? options.filter((o) => o.label.toLowerCase().includes(q)) : options.slice();
      list.innerHTML = "";
      if (!filtered.length) {
        const li = document.createElement("li");
        li.className = "combo-empty";
        li.textContent = "No matches";
        list.appendChild(li);
        activeIdx = -1; input.removeAttribute("aria-activedescendant");
        return;
      }
      filtered.forEach((o, i) => {
        const li = document.createElement("li");
        li.className = "combo-option";
        li.id = listId + "_opt" + i;
        li.setAttribute("role", "option");
        li.dataset.value = o.value;
        li.textContent = o.label;
        list.appendChild(li);
      });
      const selPos = filtered.findIndex((o) => o.value === hidden.value);
      setActive(selPos >= 0 ? selPos : 0);
    }

    function setActive(i) {
      const items = list.querySelectorAll(".combo-option");
      if (!items.length) { activeIdx = -1; return; }
      activeIdx = Math.max(0, Math.min(i, items.length - 1));
      items.forEach((li, idx) => {
        const on = idx === activeIdx;
        li.classList.toggle("active", on);
        li.setAttribute("aria-selected", on ? "true" : "false");
      });
      const active = items[activeIdx];
      input.setAttribute("aria-activedescendant", active.id);
      active.scrollIntoView({ block: "nearest" });
    }

    // Accept an exact (case-insensitive) label the user typed but didn't pick.
    function commitExact() {
      const q = input.value.trim().toLowerCase();
      const hit = options.find((o) => o.label.toLowerCase() === q);
      if (hit) commit(hit.value, hit.label);
    }

    input.addEventListener("focus", () => { if (!input.disabled) { renderList(true); open(); input.select(); } });
    input.addEventListener("input", () => { clearSelection(); renderList(false); open(); gateExecute(); });
    input.addEventListener("blur", () => {
      // Defer so an option mousedown can commit before we revert stray text.
      setTimeout(() => {
        if (!hidden.value) commitExact();
        input.value = selLabel;        // snap back to the committed label (or "")
        close();
      }, 0);
    });
    input.addEventListener("keydown", (e) => {
      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          if (!isOpen()) { renderList(true); open(); } else setActive(activeIdx + 1);
          break;
        case "ArrowUp":
          e.preventDefault();
          if (isOpen()) setActive(activeIdx - 1);
          break;
        case "Enter":
          if (isOpen() && activeIdx >= 0 && filtered[activeIdx]) {
            e.preventDefault();
            commit(filtered[activeIdx].value, filtered[activeIdx].label);
          }
          break;
        case "Escape":
          if (isOpen()) { e.preventDefault(); e.stopPropagation(); input.value = selLabel; close(); }
          break;
        case "Tab":
          close();
          break;
      }
    });
    // mousedown (not click) so the option commits before the input blurs.
    list.addEventListener("mousedown", (e) => {
      const li = e.target.closest(".combo-option");
      if (!li) return;
      e.preventDefault();
      const i = [...list.querySelectorAll(".combo-option")].indexOf(li);
      if (i >= 0 && filtered[i]) commit(filtered[i].value, filtered[i].label);
    });
    list.addEventListener("mousemove", (e) => {
      const li = e.target.closest(".combo-option");
      if (!li) return;
      const i = [...list.querySelectorAll(".combo-option")].indexOf(li);
      if (i >= 0) setActive(i);
    });

    // Fetch options and drive dynState exactly like the old loadDynamic().
    (async () => {
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
          showComboError(box, input, "(no options returned)");
          dynState[p.name] = "error";   // nothing selectable -> block execution
        } else {
          options = opts.map((o) => ({ value: o.value, label: o.label }));
          input.disabled = false;
          input.placeholder = "Type to filter…";
          if (p.default != null && p.default !== "") {
            const d = options.find((o) => o.value === p.default);
            if (d) commit(d.value, d.label);
          }
          dynState[p.name] = "ok";
        }
      } catch (e) {
        showComboError(box, input, e.message);
        dynState[p.name] = "error";
      }
      gateExecute();
    })();

    return box;
  }

  function showComboError(box, input, msg) {
    input.disabled = true;
    input.value = "";
    input.placeholder = "⚠ options unavailable";
    box.querySelector(".combo-error")?.remove();
    const err = document.createElement("div");
    err.className = "combo-error small err-text";
    err.textContent = "⚠ " + msg;
    box.appendChild(err);
  }

  // Leading "Select all" master checkbox markup for a checkbox group. Shared by
  // the static and dynamic checkbox-group paths; empty unless select_all is on.
  const selAllMarkup = (p) => p.select_all
    ? `<label class="checkbox-selall"><input type="checkbox" class="cb-selall"/> Select all</label>`
    : "";

  // Wire a group's "Select all" master checkbox to toggle every `cb_<name>`
  // option and keep its checked/indeterminate state in sync. No-op when the
  // group has no master checkbox (select_all off). Behavior is identical for
  // static and dynamic checkbox groups.
  function wireSelectAll(group, name) {
    const master = group.querySelector(".cb-selall");
    if (!master) return;
    const items = [...group.querySelectorAll(`input[name="cb_${name}"]`)];
    const syncMaster = () => {
      master.checked = items.length > 0 && items.every((b) => b.checked);
      master.indeterminate = !master.checked && items.some((b) => b.checked);
    };
    master.addEventListener("change", () => {
      items.forEach((b) => { b.checked = master.checked; });
      gateExecute();
    });
    items.forEach((b) => b.addEventListener("change", () => { syncMaster(); gateExecute(); }));
    syncMaster();
  }

  // Fetch dynamic options and render them as a checkbox group. Checkboxes share
  // the `cb_<name>` naming used by static checkbox groups, so collectValues /
  // paramEmpty handle them without special-casing the submit format.
  async function loadDynamicCheckboxes(action, p, group) {
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
        group.innerHTML = `<div class="muted small">(no options returned)</div>`;
        dynState[p.name] = "error";
        gateExecute();
        return;
      }
      const defaults = String(p.default ?? "").split(",").map((s) => s.trim()).filter(Boolean);
      const key = domKey(p.name);
      const boxes = opts.map((o) =>
        `<label><input type="checkbox" name="cb_${key}" value="${escapeAttr(o.value)}" ${
          defaults.includes(o.value) ? "checked" : ""}/> ${escapeHtml(o.label)}</label>`).join("");
      group.innerHTML = selAllMarkup(p) + boxes;
      wireSelectAll(group, key);   // no-op when select_all is off
      dynState[p.name] = "ok";
    } catch (e) {
      group.innerHTML = `<div class="err-text small">⚠ ${escapeHtml(e.message)}</div>`;
      dynState[p.name] = "error";
    }
    gateExecute();
  }

  // Enable Execute only when required fields are filled and every dynamic
  // dropdown has loaded successfully.
  function gateExecute() {
    let reason = "";
    for (const p of (current && current.parameters) || []) {
      if (p.type === "dynamic_select" || isDynamicCheckbox(p)) {
        const st = dynState[p.name];
        if (st === "loading") { reason = "Loading options…"; break; }
        if (st === "error") { reason = `"${p.name}" couldn't load`; break; }
      }
      if (p.required && paramEmpty(p)) { reason = `Fill required field: ${p.name}`; break; }
    }
    el("m-execute").disabled = !!reason;
    const note = el("m-gate");
    note.textContent = reason;
    note.classList.toggle("hidden", !reason);
  }

  function paramEmpty(p) {
    const key = domKey(p.name);
    if (p.type === "checkbox") {
      if (isDynamicCheckbox(p) || (p.options && p.options.length)) {
        return document.querySelectorAll(`input[name="cb_${key}"]:checked`).length === 0;
      }
      const node = el("f_" + key);
      return !(node && node.checked);
    }
    if (p.type === "radio") {
      return !document.querySelector(`input[name="f_${key}"]:checked`);
    }
    if (p.type === "file") {
      const zone = document.querySelector(`.dropzone[data-name="${CSS.escape(p.name)}"]`);
      return !(zone && zone.dataset.token);
    }
    const node = el("f_" + key);
    return !node || String(node.value).trim() === "";
  }

  function collectValues() {
    const values = {};
    if (!current.parameters) return values;
    for (const p of current.parameters) {
      // DOM lookups use the sanitized key; the submit key stays the literal name.
      const key = domKey(p.name);
      if (p.type === "checkbox") {
        if (isDynamicCheckbox(p) || (p.options && p.options.length)) {
          values[p.name] = [...document.querySelectorAll(`input[name="cb_${key}"]:checked`)]
            .map((n) => n.value);
        } else {
          values[p.name] = el("f_" + key).checked;
        }
      } else if (p.type === "radio") {
        const chosen = document.querySelector(`input[name="f_${key}"]:checked`);
        values[p.name] = chosen ? chosen.value : "";
      } else if (p.type === "file") {
        const zone = document.querySelector(`.dropzone[data-name="${CSS.escape(p.name)}"]`);
        values[p.name] = (zone && zone.dataset.token) || "";
      } else {
        const node = el("f_" + key);
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
    // A successful (re)connect clears any pending/shown "reconnecting" note.
    eventSource.onopen = () => {
      if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
      clearReconnectNote();
    };
    eventSource.addEventListener("stdout", (e) => appendLine(JSON.parse(e.data).line));
    // stderr is NOT an error: many tools log routine progress/info there. Render
    // it in the default terminal color (like stdout). Red is reserved for a
    // genuine failure (the catch below and the FAILED status badge).
    eventSource.addEventListener("stderr", (e) => appendLine(JSON.parse(e.data).line, "out"));
    eventSource.addEventListener("status", (e) => {
      const data = JSON.parse(e.data);
      setStatus(data.status);
      renderArtifacts(data.artifacts || []);
      closeStream();               // terminal event: we're done, stop for good
      gateExecute();
      refreshHistory();
      refreshSuccessCount();       // a run just finished — the badge may change
    });
    // The server sends SSE `id:` (line index) + honors Last-Event-ID, plus a
    // ~10s keepalive comment. So on a transient drop we must NOT close: the
    // browser auto-reconnects (readyState CONNECTING) and the server resumes
    // from Last-Event-ID with no duplicate lines. Only a FATAL error (server
    // rejected the request, e.g. a 404 for an unknown execution) puts the
    // EventSource in CLOSED with no retry — that's when we stop.
    eventSource.onerror = () => {
      const running = el("m-status").dataset.state === "RUNNING";
      if (eventSource && eventSource.readyState === EventSource.CLOSED) {
        if (running) appendLine("[connection closed]", "sys");
        closeStream();
        return;
      }
      // CONNECTING: browser is retrying on its own. Note it only if it lingers.
      if (running) scheduleReconnectNote();
    };
  }

  // Subtle, debounced "reconnecting" note so a brief blip doesn't spam the log.
  let reconnectTimer = null;
  let reconnectNoteEl = null;
  function scheduleReconnectNote() {
    if (reconnectTimer || reconnectNoteEl) return;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      if (eventSource && eventSource.readyState !== EventSource.OPEN &&
          el("m-status").dataset.state === "RUNNING") {
        const term = el("m-terminal");
        reconnectNoteEl = document.createElement("div");
        reconnectNoteEl.className = "sys";
        reconnectNoteEl.textContent = "[connection lost — reconnecting…]";
        term.appendChild(reconnectNoteEl);
        term.scrollTop = term.scrollHeight;
      }
    }, 3000);
  }
  function clearReconnectNote() {
    if (reconnectNoteEl) { reconnectNoteEl.remove(); reconnectNoteEl = null; }
  }

  function closeStream() {
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    clearReconnectNote();
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

  // ------------------------------------------------ history success badge
  // The storybook history icon shows, inside its plaque, how many stored runs
  // have succeeded. Refreshed on load, whenever a run reaches a terminal state,
  // and while the drawer polls.
  let successCount = null;
  function renderHistoryButton() {
    el("history-toggle").innerHTML =
      window.renderHistoryIcon ? window.renderHistoryIcon(successCount) : "";
  }
  async function refreshSuccessCount() {
    try {
      const res = await fetch(`${API}/executions/stats`);
      if (!res.ok) return;
      const s = await res.json();
      successCount = s.success ?? 0;
      renderHistoryButton();
    } catch (_) { /* keep the last known count */ }
  }

  // ---------------------------------------------------------------- events
  search.addEventListener("input", render);
  el("m-execute").addEventListener("click", execute);
  el("m-stop").addEventListener("click", () => stopExecution(currentExecId));
  renderHistoryButton();          // draw the icon immediately (count fills in async)
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
