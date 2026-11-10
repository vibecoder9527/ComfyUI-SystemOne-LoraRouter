// On-node LoRA Library rows. library_json stays a hidden widget so old
// workflows serialize unchanged. Vue Nodes 2.0 uses addDOMWidget; canvas
// custom widgets are a fallback only (known width/repaint limits).
//
// Add / rename uses a LiteGraph.ContextMenu chooser (className "dark" so
// ComfyUI 1.57.6 Comfy.ContextMenuFilter adds type-to-filter when there
// are more than four items), with folders nested as submenus. Cancelling
// or picking a non-usable name adds no row.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import {
  applyLoraChooserAction,
  assignLoraIds,
  blankLora,
  collectGraphTags,
  commitModel,
  isUsableLoraName,
  loraChooserMenuItems,
  loraNameFromMenuValue,
  loraNamesFromInfo,
  loraNamesFromModels,
  newLoraRowFromPick,
  parseEditorDocument,
} from "./s1_model.js";
import { mountTagChips } from "./s1_tag_chips.js";

const CSS = `
.s1-lora-node { box-sizing: border-box; width: 100%; padding: 2px 0 6px; color: var(--fg-color, #ddd); font: 12px/1.3 system-ui, sans-serif; user-select: none; }
.s1-lora-node * { box-sizing: border-box; }
.s1-lora-head, .s1-lora-row { display: flex; align-items: center; gap: 6px; }
.s1-lora-head { padding: 4px 10px 6px; opacity: 0.7; }
.s1-lora-enable-col { width: 4.8em; flex: 0 0 4.8em; display: flex; align-items: center; }
.s1-lora-head-label { flex: 1; min-width: 0; }
.s1-lora-head-strength { width: 7.2em; text-align: center; }
.s1-lora-head-tags { width: 9em; text-align: left; font-size: 11px; }
.s1-lora-row { margin: 3px 8px; padding: 4px 8px; border-radius: 10px; background: rgba(0,0,0,0.28); border: 1px solid rgba(255,255,255,0.08); }
.s1-lora-toggle { width: 18px; height: 18px; border-radius: 50%; border: 2px solid rgba(255,255,255,0.55); background: transparent; padding: 0; cursor: pointer; flex: 0 0 18px; }
.s1-lora-toggle.is-on { background: #3d9c66; border-color: #3d9c66; }
.s1-lora-name { flex: 1; min-width: 4em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; text-align: left; background: none; border: 0; color: inherit; font: inherit; padding: 2px 0; }
.s1-lora-name:hover { text-decoration: underline; }
.s1-lora-str { display: flex; align-items: center; gap: 2px; width: 7.2em; justify-content: center; flex: 0 0 7.2em; }
.s1-lora-str button { width: 18px; height: 20px; border: 0; background: transparent; color: inherit; cursor: pointer; font-size: 12px; padding: 0; }
.s1-lora-str input { width: 3.2em; text-align: center; background: transparent; border: 0; color: inherit; font: inherit; }
.s1-lora-tags { width: 9em; flex: 0 0 9em; min-width: 0; }
.s1-lora-add { display: block; width: calc(100% - 16px); margin: 6px 8px 0; padding: 7px 8px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.14); background: rgba(255,255,255,0.05); color: inherit; font: inherit; cursor: pointer; }
.s1-lora-add:hover { background: rgba(255,255,255,0.1); }
.s1-lora-menu, .s1-lora-pick { position: fixed; z-index: 99999; background: #2b2b2b; color: #eee; border: 1px solid #555; border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,0.4); padding: 4px; min-width: 220px; max-height: 320px; overflow: auto; }
.s1-lora-menu button, .s1-lora-pick button { display: block; width: 100%; text-align: left; background: none; border: 0; color: inherit; font: 12px/1.5 system-ui, sans-serif; padding: 4px 8px; cursor: pointer; }
.s1-lora-menu button:hover, .s1-lora-pick button:hover { background: #3d6ea8; }
.s1-lora-pick input { width: 100%; margin-bottom: 4px; background: #1a1a1a; color: inherit; border: 1px solid #555; border-radius: 4px; padding: 4px 6px; }
.s1-lora-pick .s1-lora-folder { font-weight: 600; opacity: 0.75; padding: 4px 8px; }
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

function liteGraph() {
  return (typeof LiteGraph !== "undefined" && LiteGraph)
    || (typeof globalThis !== "undefined" && globalThis.LiteGraph)
    || app?.LiteGraph
    || null;
}

function closePopups() {
  if (typeof document === "undefined") return;
  document.querySelectorAll(".s1-lora-menu, .s1-lora-pick").forEach((el) => el.remove());
}

function placePopup(el, event) {
  document.body.appendChild(el);
  const x = event?.clientX ?? 80;
  const y = event?.clientY ?? 80;
  el.style.left = `${Math.min(x, window.innerWidth - 240)}px`;
  el.style.top = `${Math.min(y, window.innerHeight - 220)}px`;
  const close = (evt) => {
    if (el.contains(evt.target)) return;
    el.remove();
    document.removeEventListener("mousedown", close, true);
  };
  setTimeout(() => document.addEventListener("mousedown", close, true), 0);
}

function showFallbackChooser(event, names, onPick) {
  closePopups();
  const box = document.createElement("div");
  box.className = "s1-lora-pick";
  const filter = document.createElement("input");
  filter.placeholder = "Filter LoRAs…";
  const list = document.createElement("div");
  const render = () => {
    const q = filter.value.trim().toLowerCase();
    list.replaceChildren();
    const matches = (names || []).filter((name) => !q || String(name).toLowerCase().includes(q));
    if (!matches.length) {
      const empty = document.createElement("div");
      empty.textContent = names?.length ? "No matches." : "No LoRA names from this ComfyUI (check /models/loras).";
      empty.style.padding = "6px 8px";
      list.append(empty);
      return;
    }
    const items = loraChooserMenuItems(matches);
    const paint = (entries, into) => {
      for (const entry of entries) {
        if (entry.has_submenu) {
          const label = document.createElement("div");
          label.className = "s1-lora-folder";
          label.textContent = entry.content;
          into.append(label);
          paint(entry.submenu?.options || [], into);
        } else {
          const button = document.createElement("button");
          button.type = "button";
          button.textContent = entry.content;
          button.title = entry.s1LoraName || entry.value || entry.content;
          button.addEventListener("click", () => {
            const picked = loraNameFromMenuValue(entry);
            if (isUsableLoraName(picked)) onPick(picked);
            box.remove();
          });
          into.append(button);
        }
      }
    };
    paint(items, list);
  };
  filter.addEventListener("input", render);
  box.append(filter, list);
  placePopup(box, event);
  render();
  filter.focus();
}

export function showLoraChooser(event, names, onPick) {
  const LG = liteGraph();
  const items = loraChooserMenuItems(names);
  const callback = (value) => {
    const picked = loraNameFromMenuValue(value);
    if (isUsableLoraName(picked)) onPick(picked);
  };
  if (LG && typeof LG.ContextMenu === "function") {
    const scale = Math.max(1, app?.canvas?.ds?.scale ?? 1);
    // className "dark" + more than 4 items: Comfy.ContextMenuFilter in frontend
    // 1.57.6 injects the type-to-filter search box.
    new LG.ContextMenu(items.length ? items : [{ content: "No LoRAs found", disabled: true }], {
      event,
      title: "Choose a lora",
      scale,
      className: "dark",
      callback,
    });
    return { style: "litegraph" };
  }
  showFallbackChooser(event, names, onPick);
  return { style: "fallback" };
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
  const enableTitle = document.createElement("div");
  enableTitle.className = "s1-lora-enable-col";
  enableTitle.textContent = "預設啟用";
  const nameTitle = document.createElement("div");
  nameTitle.className = "s1-lora-head-label";
  const strengthTitle = document.createElement("div");
  strengthTitle.className = "s1-lora-head-strength";
  strengthTitle.textContent = "Strength";
  const tagsTitle = document.createElement("div");
  tagsTitle.className = "s1-lora-head-tags";
  tagsTitle.textContent = "Tags";
  head.append(enableTitle, nameTitle, strengthTitle, tagsTitle);
  host.append(head);

  loras.forEach((entry, index) => {
    const row = document.createElement("div");
    row.className = "s1-lora-row";
    row.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      showRowMenu(event, node, index);
    });

    const enableCol = document.createElement("div");
    enableCol.className = "s1-lora-enable-col";
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "s1-lora-toggle" + (entry.enabled_default === false ? "" : " is-on");
    toggle.title = "enabled_default (off means not applied by default; tag hits still apply)";
    toggle.addEventListener("click", () => {
      entry.enabled_default = entry.enabled_default === false;
      writeLibrary(node, model);
      renderLibrary(node);
    });
    enableCol.append(toggle);

    const name = document.createElement("button");
    name.type = "button";
    name.className = "s1-lora-name";
    name.textContent = entry.name || "None";
    name.title = entry.name || "Click to pick a LoRA";
    name.addEventListener("click", async (event) => {
      const names = await loadLoraNames();
      showLoraChooser(event, names, (picked) => {
        const result = applyLoraChooserAction(model.loras, "swap", picked, index);
        model.loras = result.loras;
        if (result.changed) writeLibrary(node, model);
        renderLibrary(node);
      });
    });

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

    const tagsWrap = document.createElement("div");
    tagsWrap.className = "s1-lora-tags";
    tagsWrap.append(mountTagChips({
      tags: entry.tags || [],
      suggestions: tags,
      listId,
      onChange: (next) => {
        entry.tags = next;
        writeLibrary(node, model);
      },
    }));

    row.append(enableCol, name, strengthBox, tagsWrap);
    host.append(row);
  });

  const datalist = document.createElement("datalist");
  datalist.id = listId;
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
    showLoraChooser(event, names, (picked) => {
      const result = applyLoraChooserAction(model.loras, "add", picked);
      model.loras = result.loras;
      if (result.changed) writeLibrary(node, model);
      renderLibrary(node);
    });
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
