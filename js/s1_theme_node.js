// On-node Theme Root / Theme editor. theme_json stays a hidden widget so old
// workflows serialize unchanged. Vue Nodes 2.0 uses addDOMWidget; canvas
// custom widgets are a fallback only (known width/repaint limits).

import { app } from "../../scripts/app.js";
import {
  addThemeOption,
  assignThemeDocument,
  collectGraphTags,
  commitModel,
  compactOptionOutputs,
  DEFAULT_NONE_LABEL,
  deleteThemeOption,
  ensureDefaultNoneOption,
  expandOptionOutputs,
  moveThemeOption,
  optionDisplayOrder,
  orderThemePromptInputs,
  parseEditorDocument,
  planOptionOutputs,
  relinkOptionSlots,
} from "./s1_model.js";
import { mountTagChips } from "./s1_tag_chips.js";

const CSS = `
.s1-theme-node { box-sizing: border-box; width: 100%; padding: 2px 0 6px; color: var(--fg-color, #ddd); font: 12px/1.3 system-ui, sans-serif; }
.s1-theme-node * { box-sizing: border-box; }
.s1-theme-title { padding: 4px 10px 2px; font-weight: 600; }
.s1-theme-desc { display: block; width: calc(100% - 16px); margin: 0 8px 8px; min-height: 64px; resize: vertical; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); color: inherit; font: inherit; border-radius: 8px; padding: 6px 8px; }
.s1-theme-table { width: calc(100% - 16px); margin: 0 8px; border-collapse: collapse; table-layout: fixed; }
.s1-theme-table th { text-align: left; font-weight: 500; opacity: 0.7; padding: 4px 6px; }
.s1-theme-table td { padding: 3px 6px; vertical-align: middle; }
.s1-theme-table .col-opt { width: 3.2em; text-align: center; }
.s1-theme-table .col-desc { width: auto; }
.s1-theme-table .col-tags { width: 11em; }
.s1-theme-table input.s1-theme-desc-cell { width: 100%; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); color: inherit; font: inherit; border-radius: 6px; padding: 3px 6px; }
.s1-theme-table tr.is-none td { font-style: italic; }
.s1-theme-table tr.is-none .s1-theme-none-label { padding: 3px 6px; }
.s1-theme-add { display: block; width: calc(100% - 16px); margin: 8px 8px 0; padding: 7px 8px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.14); background: rgba(255,255,255,0.05); color: inherit; font: inherit; cursor: pointer; }
.s1-theme-add:hover { background: rgba(255,255,255,0.1); }
.s1-theme-menu { position: fixed; z-index: 99999; background: #2b2b2b; color: #eee; border: 1px solid #555; border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,0.4); padding: 4px; min-width: 160px; }
.s1-theme-menu button { display: block; width: 100%; text-align: left; background: none; border: 0; color: inherit; font: 12px/1.5 system-ui, sans-serif; padding: 4px 8px; cursor: pointer; }
.s1-theme-menu button:hover { background: #3d6ea8; }
.s1-theme-menu button:disabled { opacity: 0.45; cursor: default; }
`;

let styleInjected = false;
function injectStyle() {
  if (styleInjected || typeof document === "undefined") return;
  const el = document.createElement("style");
  el.id = "s1-theme-node-style";
  el.textContent = CSS;
  document.head.appendChild(el);
  styleInjected = true;
}

function isThemeNode(node) {
  const name = node?.comfyClass || node?.constructor?.comfyClass || node?.type || "";
  return name === "S1ThemeRoot" || name === "S1Theme";
}

function findWidget(node, name) {
  return (node?.widgets || []).find((widget) => widget?.name === name) || null;
}

function hideThemeJsonWidget(node) {
  const widget = findWidget(node, "theme_json");
  if (!widget) return null;
  widget.hidden = true;
  widget.computeSize = () => [0, -4];
  widget.options = { ...(widget.options || {}), hidden: true };
  return widget;
}

function readTheme(node) {
  const widget = findWidget(node, "theme_json");
  const raw = widget && widget.value != null ? String(widget.value) : '{ "options": [] }';
  const parsed = parseEditorDocument("theme", raw);
  if (!parsed.ok) return { options: [], instructions: "", error: parsed.error };
  assignThemeDocument(parsed.model);
  ensureDefaultNoneOption(parsed.model);
  return parsed.model;
}

function writeTheme(node, model) {
  assignThemeDocument(model);
  ensureDefaultNoneOption(model);
  const committed = commitModel("theme", model);
  if (!committed.ok) return false;
  const widget = findWidget(node, "theme_json");
  if (widget) widget.value = committed.json;
  syncThemeOutputs(node);
  node.setDirtyCanvas?.(true, true);
  node.graph?.setDirtyCanvas?.(true, true);
  return true;
}

function syncThemeOutputs(node) {
  orderThemePromptInputs(node);
  const plan = planOptionOutputs(findWidget(node, "theme_json")?.value ?? "");
  if (!plan.ok || !Array.isArray(plan.slots)) return;
  expandOptionOutputs(node);
  relinkOptionSlots(node, plan.slots);
  const model = readTheme(node);
  compactOptionOutputs(node, model.none_option_id);
}

function closeMenus() {
  if (typeof document === "undefined") return;
  document.querySelectorAll(".s1-theme-menu").forEach((el) => el.remove());
}

function placePopup(box, event) {
  document.body.append(box);
  const x = Math.min(event.clientX, window.innerWidth - box.offsetWidth - 8);
  const y = Math.min(event.clientY, window.innerHeight - box.offsetHeight - 8);
  box.style.left = `${Math.max(8, x)}px`;
  box.style.top = `${Math.max(8, y)}px`;
  const dismiss = (later) => {
    if (later.target && box.contains(later.target)) return;
    box.remove();
    window.removeEventListener("mousedown", dismiss, true);
  };
  window.setTimeout(() => window.addEventListener("mousedown", dismiss, true), 0);
}

function showRowMenu(event, node, optionId) {
  closeMenus();
  const model = readTheme(node);
  const noneId = String(model.none_option_id || "");
  if (String(optionId) === noneId) return;
  const displayed = optionDisplayOrder(model.options, noneId).filter((option) => String(option.option_id) !== noneId);
  const pos = displayed.findIndex((option) => String(option.option_id) === String(optionId));
  const box = document.createElement("div");
  box.className = "s1-theme-menu";
  const items = [
    ["Move up", pos > 0, () => moveThemeOption(model, optionId, -1)],
    ["Move down", pos >= 0 && pos < displayed.length - 1, () => moveThemeOption(model, optionId, 1)],
    ["Delete", true, () => deleteThemeOption(model, optionId)],
  ];
  for (const [label, enabled, act] of items) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.disabled = !enabled;
    if (enabled) {
      button.addEventListener("click", () => {
        act();
        writeTheme(node, model);
        renderTheme(node);
        box.remove();
      });
    }
    box.append(button);
  }
  placePopup(box, event);
}

function optionText(option) {
  const label = option?.label != null ? String(option.label).trim() : "";
  const description = option?.description != null ? String(option.description).trim() : "";
  return label || description;
}

function renderTheme(node) {
  const host = node.__s1ThemeHost;
  if (!host) return;
  const model = readTheme(node);
  const noneId = String(model.none_option_id || "");
  const rows = optionDisplayOrder(model.options || [], noneId);
  const tags = collectGraphTags(node.graph || app.graph, node);
  const listId = `s1-theme-tag-list-${node.id ?? "new"}`;
  host.replaceChildren();

  const heading = document.createElement("div");
  heading.className = "s1-theme-title";
  heading.textContent = "Theme";
  const desc = document.createElement("textarea");
  desc.className = "s1-theme-desc";
  desc.placeholder = "Description Here";
  desc.value = model.instructions != null ? String(model.instructions) : "";
  desc.addEventListener("change", () => {
    model.instructions = desc.value;
    writeTheme(node, model);
  });
  host.append(heading, desc);

  const table = document.createElement("table");
  table.className = "s1-theme-table";
  const thead = document.createElement("thead");
  thead.innerHTML = "<tr><th class='col-opt'>Option</th><th class='col-desc'>Description</th><th class='col-tags'>Tags (Comma)</th></tr>";
  table.append(thead);
  const tbody = document.createElement("tbody");

  rows.forEach((option, index) => {
    const isNone = String(option.option_id) === noneId;
    const tr = document.createElement("tr");
    if (isNone) tr.className = "is-none";
    if (!isNone) {
      tr.addEventListener("contextmenu", (event) => {
        event.preventDefault();
        showRowMenu(event, node, option.option_id);
      });
    }

    const num = document.createElement("td");
    num.className = "col-opt";
    num.textContent = String(index + 1);

    const descCell = document.createElement("td");
    descCell.className = "col-desc";
    if (isNone) {
      const locked = document.createElement("div");
      locked.className = "s1-theme-none-label";
      locked.textContent = optionText(option) || DEFAULT_NONE_LABEL;
      descCell.append(locked);
    } else {
      const field = document.createElement("input");
      field.type = "text";
      field.className = "s1-theme-desc-cell";
      field.value = optionText(option);
      field.addEventListener("change", () => {
        option.label = field.value;
        option.description = field.value;
        writeTheme(node, model);
      });
      descCell.append(field);
    }

    const tagCell = document.createElement("td");
    tagCell.className = "col-tags";
    const chips = mountTagChips({
      tags: option.tags || [],
      suggestions: tags,
      listId,
      locked: isNone,
      onChange: (next) => {
        option.tags = next;
        writeTheme(node, model);
      },
    });
    tagCell.append(chips);

    tr.append(num, descCell, tagCell);
    tbody.append(tr);
  });
  table.append(tbody);
  host.append(table);

  const datalist = document.createElement("datalist");
  datalist.id = listId;
  for (const tag of tags) {
    const item = document.createElement("option");
    item.value = tag;
    datalist.append(item);
  }
  host.append(datalist);

  const add = document.createElement("button");
  add.type = "button";
  add.className = "s1-theme-add";
  add.textContent = "Add option";
  add.addEventListener("click", () => {
    const result = addThemeOption(model);
    if (!result.ok) return;
    writeTheme(node, model);
    renderTheme(node);
  });
  host.append(add);

  const height = 36 + 80 + 28 + rows.length * 34 + 44;
  if (Array.isArray(node.size)) {
    node.size[0] = Math.max(node.size[0] || 0, 460);
    node.size[1] = Math.max(height + 40, 160);
  }
  node.setSize?.(node.size);
  node.setDirtyCanvas?.(true, true);
}

export function installThemeNode(node) {
  if (!isThemeNode(node) || node.__s1ThemeNode) return;
  node.__s1ThemeNode = true;
  injectStyle();
  hideThemeJsonWidget(node);

  const host = document.createElement("div");
  host.className = "s1-theme-node";
  node.__s1ThemeHost = host;

  const options = { hideOnZoom: false, serialize: false, getMinHeight: () => 160 };
  if (typeof node.addDOMWidget === "function") {
    const widget = node.addDOMWidget("s1_theme_rows", "s1_theme_rows", host, options);
    if (widget) {
      widget.serialize = false;
      widget.options = { ...(widget.options || {}), serialize: false, hidden: false };
    }
  } else if (typeof node.addCustomWidget === "function") {
    node.addCustomWidget({
      name: "s1_theme_rows",
      type: "s1_theme_rows",
      serialize: false,
      draw() {},
      computeSize: () => [460, ((readTheme(node).options || []).length) * 34 + 180],
    });
    const attach = () => {
      const el = node.vueHost || node.container || null;
      if (el && !host.isConnected) el.append(host);
    };
    attach();
    setTimeout(attach, 0);
  }

  const originalConfigure = node.onConfigure;
  node.onConfigure = function s1ThemeConfigure(...args) {
    const result = typeof originalConfigure === "function" ? originalConfigure.apply(this, args) : undefined;
    hideThemeJsonWidget(this);
    const model = readTheme(this);
    if (model && !model.error) writeTheme(this, model);
    renderTheme(this);
    return result;
  };

  renderTheme(node);
}
