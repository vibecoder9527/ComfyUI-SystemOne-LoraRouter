// On-node LoRA Library rows, styled after rgthree Power Lora Loader.
// library_json stays a hidden widget so old workflows serialize unchanged.
// Vue Nodes 2.0 (Comfy.VueNodes.Enabled) is DOM-based: addDOMWidget is the
// supported path. Canvas custom widgets are hosted in WidgetLegacy and have
// known width/repaint issues, so they are only a fallback.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import {
  assignLoraIds,
  blankLora,
  collectGraphTags,
  commitModel,
  loraNamesFromInfo,
  loraNamesFromModels,
  parseEditorDocument,
} from "./s1_model.js";

const CSS = `
.s1-lora-node { box-sizing: border-box; width: 100%; padding: 2px 0 6px; color: var(--fg-color, #ddd); font: 12px/1.3 system-ui, sans-serif; user-select: none; }
.s1-lora-node * { box-sizing: border-box; }
.s1-lora-head, .s1-lora-row { display: flex; align-items: center; gap: 6px; }
.s1-lora-head { padding: 4px 10px 6px; opacity: 0.7; }
.s1-lora-head-label { flex: 1; min-width: 0; }
.s1-lora-head-strength { width: 7.2em; text-align: center; }
.s1-lora-head-tags { width: 9em; text-align: left; font-size: 11px; }
.s1-lora-row { margin: 3px 8px; padding: 4px 8px; border-radius: 10px; background: rgba(0,0,0,0.28); border: 1px solid rgba(255,255,255,0.08); }
.s1-lora-row.is-off { opacity: 0.45; }
.s1-lora-toggle { width: 18px; height: 18px; border-radius: 50%; border: 2px solid rgba(255,255,255,0.55); background: transparent; padding: 0; cursor: pointer; flex: 0 0 18px; }
.s1-lora-toggle.is-on { background: #3d9c66; border-color: #3d9c66; }
.s1-lora-toggle.is-mixed { background: linear-gradient(90deg, #3d9c66 50%, transparent 50%); }
.s1-lora-name { flex: 1; min-width: 4em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; text-align: left; background: none; border: 0; color: inherit; font: inherit; padding: 2px 0; }
.s1-lora-name:hover { text-decoration: underline; }
.s1-lora-info { width: 20px; height: 20px; border: 0; border-radius: 50%; background: rgba(255,255,255,0.08); color: inherit; cursor: pointer; font: 12px/20px Georgia, serif; padding: 0; }
.s1-lora-str { display: flex; align-items: center; gap: 2px; width: 7.2em; justify-content: center; flex: 0 0 7.2em; }
.s1-lora-str button { width: 18px; height: 20px; border: 0; background: transparent; color: inherit; cursor: pointer; font-size: 12px; padding: 0; }
.s1-lora-str input { width: 3.2em; text-align: center; background: transparent; border: 0; color: inherit; font: inherit; }
.s1-lora-tags { width: 9em; flex: 0 0 9em; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); color: inherit; font: inherit; border-radius: 6px; padding: 3px 6px; }
.s1-lora-add { display: block; width: calc(100% - 16px); margin: 6px 8px 0; padding: 7px 8px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.14); background: rgba(255,255,255,0.05); color: inherit; font: inherit; cursor: pointer; }
.s1-lora-add:hover { background: rgba(255,255,255,0.1); }
.s1-lora-menu, .s1-lora-pick, .s1-lora-info-pop { position: fixed; z-index: 99999; background: #2b2b2b; color: #eee; border: 1px solid #555; border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,0.4); padding: 4px; min-width: 180px; max-height: 280px; overflow: auto; }
.s1-lora-menu button, .s1-lora-pick button { display: block; width: 100%; text-align: left; background: none; border: 0; color: inherit; font: 12px/1.5 system-ui, sans-serif; padding: 4px 8px; cursor: pointer; }
.s1-lora-menu button:hover, .s1-lora-pick button:hover { background: #3d6ea8; }
.s1-lora-info-pop { padding: 10px 12px; max-width: 360px; font: 12px/1.45 system-ui, sans-serif; }
.s1-lora-info-pop dt { opacity: 0.65; }
.s1-lora-info-pop dd { margin: 0 0 6px; word-break: break-all; }
`;

let styleInjected = false;
function injectStyle() {
  if (styleInjected || typeof document === "undefined") return;
  const el = document.createElement("style");
  el.id = "s1-lora-node-style";
  el.textContent = CSS;
  document.head.appendChild(el);
  styleInjected = true;
}

function isLibraryNode(node) {
  const name = node?.comfyClass || node?.constructor?.comfyClass || node?.type || "";
  return name === "S1LoraLibrary";
}

function findWidget(node, name) {
  return (node?.widgets || []).find((widget) => widget?.name === name) || null;
}

function hideLibraryJsonWidget(node) {
  const widget = findWidget(node, "library_json");
  if (!widget) return null;
  widget.hidden = true;
  widget.computeSize = () => [0, -4];
  widget.options = { ...(widget.options || {}), hidden: true };
  return widget;
}

function readLibrary(node) {
  const widget = findWidget(node, "library_json");
  const raw = widget && widget.value != null ? String(widget.value) : '{ "loras": [] }';
  const parsed = parseEditorDocument("lora", raw);
  if (!parsed.ok) return { loras: [], version: 1, error: parsed.error };
  assignLoraIds(parsed.model);
  return parsed.model;
}

function writeLibrary(node, model) {
  assignLoraIds(model);
  const committed = commitModel("lora", model);
  if (!committed.ok) return false;
  const widget = findWidget(node, "library_json");
  if (widget) widget.value = committed.json;
  node.setDirtyCanvas?.(true, true);
  node.graph?.setDirtyCanvas?.(true, true);
  return true;
}

function fmtStrength(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "1.00";
  return number.toFixed(2);
}

function parseTags(text) {
  return String(text || "").split(/[\s,]+/).map((item) => item.trim()).filter(Boolean);
}

let loraNamesCache = { status: "idle", names: [] };

async function loadLoraNames() {
  if (loraNamesCache.status === "ready" && loraNamesCache.names.length) return loraNamesCache.names;
  const tryInfo = async (data) => loraNamesFromInfo(data);
  try {
    if (api && typeof api.getNodeDefs === "function") {
      const names = tryInfo(await api.getNodeDefs());
      if (names?.length) {
        loraNamesCache = { status: "ready", names };
        return names;
      }
    }
  } catch (exc) {
    console.warn("[S1] getNodeDefs failed", exc);
  }
  for (const route of ["/object_info/LoraLoader", "/object_info/LoraLoaderModelOnly", "/object_info", "/models/loras"]) {
    try {
      const response = await fetch(route);
      if (!response.ok) continue;
      const data = await response.json();
      const names = route.endsWith("loras") ? loraNamesFromModels(data) : tryInfo(data);
      if (names?.length) {
        loraNamesCache = { status: "ready", names };
        return names;
      }
    } catch (exc) {
      console.warn(`[S1] ${route} failed`, exc);
    }
  }
  loraNamesCache = { status: "ready", names: [] };
  return [];
}

function closePopups() {
  document.querySelectorAll(".s1-lora-menu, .s1-lora-pick, .s1-lora-info-pop").forEach((el) => el.remove());
}

function placePopup(el, event) {
  document.body.appendChild(el);
  const x = event.clientX ?? 80;
  const y = event.clientY ?? 80;
  el.style.left = `${Math.min(x, window.innerWidth - 220)}px`;
  el.style.top = `${Math.min(y, window.innerHeight - 200)}px`;
  const close = (evt) => {
    if (el.contains(evt.target)) return;
    el.remove();
    document.removeEventListener("mousedown", close, true);
  };
  setTimeout(() => document.addEventListener("mousedown", close, true), 0);
}

function showChooser(event, names, onPick) {
  closePopups();
  const box = document.createElement("div");
  box.className = "s1-lora-pick";
  const filter = document.createElement("input");
  filter.placeholder = "Filter LoRAs…";
  filter.style.cssText = "width:100%;margin-bottom:4px;background:#1a1a1a;color:inherit;border:1px solid #555;border-radius:4px;padding:4px 6px;";
  const list = document.createElement("div");
  const render = () => {
    const q = filter.value.trim().toLowerCase();
    list.replaceChildren();
    const matches = names.filter((name) => !q || String(name).toLowerCase().includes(q)).slice(0, 200);
    if (!matches.length) {
      const empty = document.createElement("div");
      empty.textContent = names.length ? "No matches." : "No LoRA names from this ComfyUI (check /models/loras).";
      empty.style.padding = "6px 8px";
      list.append(empty);
      return;
    }
    for (const name of matches) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = name;
      button.addEventListener("click", () => {
        onPick(name);
        box.remove();
      });
      list.append(button);
    }
  };
  filter.addEventListener("input", render);
  box.append(filter, list);
  placePopup(box, event);
  render();
  filter.focus();
}

function showInfo(event, entry) {
  closePopups();
  const box = document.createElement("div");
  box.className = "s1-lora-info-pop";
  box.innerHTML = `<dl>
    <dt>lora_id</dt><dd></dd>
    <dt>name</dt><dd></dd>
    <dt>strength (model &amp; clip)</dt><dd></dd>
    <dt>enabled_default</dt><dd></dd>
    <dt>tags</dt><dd></dd>
  </dl>`;
  const dds = box.querySelectorAll("dd");
  dds[0].textContent = entry.lora_id || "";
  dds[1].textContent = entry.name || "";
  dds[2].textContent = fmtStrength(entry.strength_model ?? entry.strength ?? 1);
  dds[3].textContent = entry.enabled_default === false ? "false" : "true";
  dds[4].textContent = Array.isArray(entry.tags) ? entry.tags.join(", ") : "";
  placePopup(box, event);
}

function showRowMenu(event, node, index) {
  closePopups();
  const model = readLibrary(node);
  const box = document.createElement("div");
  box.className = "s1-lora-menu";
  const items = [
    ["Move up", index > 0, () => {
      const [row] = model.loras.splice(index, 1);
      model.loras.splice(index - 1, 0, row);
    }],
    ["Move down", index < model.loras.length - 1, () => {
      const [row] = model.loras.splice(index, 1);
      model.loras.splice(index + 1, 0, row);
    }],
    ["Delete", true, () => {
      model.loras.splice(index, 1);
    }],
  ];
  for (const [label, enabled, act] of items) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.disabled = !enabled;
    if (enabled) {
      button.addEventListener("click", () => {
        act();
        writeLibrary(node, model);
        renderLibrary(node);
        box.remove();
      });
    }
    box.append(button);
  }
  placePopup(box, event);
}

function allEnabledState(loras) {
  if (!loras.length) return false;
  const on = loras.every((row) => row.enabled_default !== false);
  const off = loras.every((row) => row.enabled_default === false);
  if (on) return true;
  if (off) return false;
  return null;
}

function renderLibrary(node) {
  const host = node.__s1LoraHost;
  if (!host) return;
  const model = readLibrary(node);
  const loras = Array.isArray(model.loras) ? model.loras : [];
  const tags = collectGraphTags(node.graph || app.graph, node);
  const listId = `s1-lora-tag-list-${node.id ?? "new"}`;
  host.replaceChildren();

  const head = document.createElement("div");
  head.className = "s1-lora-head";
  const allState = allEnabledState(loras);
  const allToggle = document.createElement("button");
  allToggle.type = "button";
  allToggle.className = "s1-lora-toggle" + (allState === true ? " is-on" : allState === null ? " is-mixed" : "");
  allToggle.title = "Toggle All";
  allToggle.addEventListener("click", () => {
    const next = allState !== true;
    for (const row of loras) row.enabled_default = next;
    writeLibrary(node, model);
    renderLibrary(node);
  });
  const allLabel = document.createElement("div");
  allLabel.className = "s1-lora-head-label";
  allLabel.textContent = "Toggle All";
  const strengthTitle = document.createElement("div");
  strengthTitle.className = "s1-lora-head-strength";
  strengthTitle.textContent = "Strength";
  const tagsTitle = document.createElement("div");
  tagsTitle.className = "s1-lora-head-tags";
  tagsTitle.textContent = "Tags";
  head.append(allToggle, allLabel, strengthTitle, tagsTitle);
  host.append(head);

  loras.forEach((entry, index) => {
    const row = document.createElement("div");
    row.className = "s1-lora-row" + (entry.enabled_default === false ? " is-off" : "");
    row.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      showRowMenu(event, node, index);
    });

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "s1-lora-toggle" + (entry.enabled_default === false ? "" : " is-on");
    toggle.title = "enabled_default";
    toggle.addEventListener("click", () => {
      entry.enabled_default = entry.enabled_default === false;
      writeLibrary(node, model);
      renderLibrary(node);
    });

    const name = document.createElement("button");
    name.type = "button";
    name.className = "s1-lora-name";
    name.textContent = entry.name || "None";
    name.title = entry.name || "Click to pick a LoRA";
    name.addEventListener("click", async (event) => {
      const names = await loadLoraNames();
      showChooser(event, names, (picked) => {
        entry.name = picked;
        writeLibrary(node, model);
        renderLibrary(node);
      });
    });

    const info = document.createElement("button");
    info.type = "button";
    info.className = "s1-lora-info";
    info.textContent = "i";
    info.title = "Info";
    info.addEventListener("click", (event) => showInfo(event, entry));

    const strengthBox = document.createElement("div");
    strengthBox.className = "s1-lora-str";
    const dec = document.createElement("button");
    dec.type = "button";
    dec.textContent = "◀";
    const val = document.createElement("input");
    val.type = "text";
    val.value = fmtStrength(entry.strength_model ?? 1);
    const inc = document.createElement("button");
    inc.type = "button";
    inc.textContent = "▶";
    const applyStrength = (next) => {
      const number = Math.round(Number(next) * 100) / 100;
      if (!Number.isFinite(number)) {
        val.value = fmtStrength(entry.strength_model ?? 1);
        return;
      }
      entry.strength_model = number;
      entry.strength_clip = number;
      val.value = fmtStrength(number);
      writeLibrary(node, model);
    };
    dec.addEventListener("click", () => applyStrength((Number(entry.strength_model) || 0) - 0.05));
    inc.addEventListener("click", () => applyStrength((Number(entry.strength_model) || 0) + 0.05));
    val.addEventListener("change", () => applyStrength(val.value));
    let drag = null;
    const onMove = (event) => {
      if (drag == null) return;
      applyStrength(drag.start + (event.clientX - drag.x) * 0.05);
    };
    const onUp = () => {
      drag = null;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    strengthBox.addEventListener("mousedown", (event) => {
      if (event.button !== 0) return;
      if (event.target === val) return;
      drag = { x: event.clientX, start: Number(entry.strength_model) || 1 };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    });
    strengthBox.append(dec, val, inc);

    const tagsInput = document.createElement("input");
    tagsInput.className = "s1-lora-tags";
    tagsInput.setAttribute("list", listId);
    tagsInput.placeholder = "tags";
    tagsInput.value = Array.isArray(entry.tags) ? entry.tags.join(", ") : "";
    tagsInput.addEventListener("change", () => {
      entry.tags = parseTags(tagsInput.value);
      writeLibrary(node, model);
    });

    row.append(toggle, name, info, strengthBox, tagsInput);
    host.append(row);
  });

  const datalist = document.createElement("datalist");
  datalist.id = listId;
  datalist.replaceChildren();
  for (const tag of tags) {
    const option = document.createElement("option");
    option.value = tag;
    datalist.append(option);
  }
  host.append(datalist);

  const add = document.createElement("button");
  add.type = "button";
  add.className = "s1-lora-add";
  add.textContent = "＋ Add Lora";
  add.addEventListener("click", async (event) => {
    const names = await loadLoraNames();
    const create = (name) => {
      const row = blankLora();
      if (name) row.name = name;
      model.loras.push(row);
      writeLibrary(node, model);
      renderLibrary(node);
    };
    if (names.length) showChooser(event, names, create);
    else create("");
  });
  host.append(add);

  const height = 36 + loras.length * 40 + 44;
  if (Array.isArray(node.size)) {
    node.size[0] = Math.max(node.size[0] || 0, 420);
    node.size[1] = Math.max(height + 40, 80);
  }
  node.setSize?.(node.size);
  node.setDirtyCanvas?.(true, true);
}

export function installLoraLibraryNode(node) {
  if (!isLibraryNode(node) || node.__s1LoraNode) return;
  node.__s1LoraNode = true;
  injectStyle();
  hideLibraryJsonWidget(node);

  const host = document.createElement("div");
  host.className = "s1-lora-node";
  node.__s1LoraHost = host;

  const options = { hideOnZoom: false, serialize: false, getMinHeight: () => 80 };
  if (typeof node.addDOMWidget === "function") {
    const widget = node.addDOMWidget("s1_lora_rows", "s1_lora_rows", host, options);
    if (widget) {
      widget.serialize = false;
      widget.options = { ...(widget.options || {}), serialize: false, hidden: false };
    }
  } else if (typeof node.addCustomWidget === "function") {
    node.addCustomWidget({
      name: "s1_lora_rows",
      type: "s1_lora_rows",
      serialize: false,
      draw() {},
      computeSize: () => [420, (readLibrary(node).loras || []).length * 40 + 80],
    });
    // Without addDOMWidget the HTML host is attached after the node element if possible.
    const attach = () => {
      const el = node.vueHost || node.container || null;
      if (el && !host.isConnected) el.append(host);
    };
    attach();
    setTimeout(attach, 0);
  }

  const originalConfigure = node.onConfigure;
  node.onConfigure = function s1LoraConfigure(...args) {
    const result = typeof originalConfigure === "function" ? originalConfigure.apply(this, args) : undefined;
    hideLibraryJsonWidget(this);
    const model = readLibrary(this);
    if (model && !model.error) writeLibrary(this, model);
    renderLibrary(this);
    return result;
  };

  renderLibrary(node);
  loadLoraNames();
}
