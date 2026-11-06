// Visual editors for LoRA Library, Theme Library, and Theme Sequence.
// ComfyUI loads this module because __init__.py exports WEB_DIRECTORY = "./js".

import { app } from "../../scripts/app.js";
import {
  ACTION_TYPES,
  SELECT_MODES,
  WHEN_OPS,
  blankAction,
  blankBinding,
  blankDependency,
  blankLora,
  blankOption,
  blankStep,
  blankTheme,
  commitModel,
  parseEditorDocument,
  splitList,
} from "./s1_model.js";

const TAB_ID = "s1-lora-router";
const BUTTON_NAME = "Open visual editor";
const BUTTON_LABEL = "Open visual editor";

const NODE_SPECS = {
  S1LoraLibrary: { kind: "lora", widget: "library_json", title: "LoRA Library" },
  S1ThemeLibrary: { kind: "theme", widget: "library_json", title: "Theme Library" },
  S1ThemeSequence: { kind: "sequence", widget: "sequence_json", title: "Theme Sequence" },
};

const FACTORIES = {
  lora: blankLora,
  theme: blankTheme,
  option: blankOption,
  binding: blankBinding,
  step: blankStep,
  dependency: blankDependency,
  action: () => blankAction("enable_step"),
};

const OP_HINT = {
  eq: "Selected option equals this id. Use one id.",
  neq: "Selected option is not this id. Use one id.",
  includes_any: "Selected set intersects these ids.",
  includes_all: "Selected set contains every id.",
  skipped: "The earlier step was skipped. No option ids.",
  answered: "The earlier step returned an answer. No option ids.",
};

const CSS = `
.s1-editor, .s1-editor * { box-sizing: border-box; }
.s1-editor {
  color: inherit;
  font: 13px/1.4 system-ui, sans-serif;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
}
.s1-editor-modal-host > .s1-editor { min-height: 100%; }
.s1-editor h2, .s1-editor h3 { margin: 0; font-size: 13px; font-weight: 650; }
.s1-editor .s1-header { overflow-wrap: anywhere; }
.s1-editor .s1-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  position: sticky;
  top: 0;
  z-index: 1;
  padding: 2px 0 4px;
}
.s1-editor button, .s1-editor-modal button {
  background: color-mix(in srgb, currentColor 12%, transparent);
  color: inherit;
  border: 1px solid color-mix(in srgb, currentColor 30%, transparent);
  border-radius: 4px;
  padding: 4px 8px;
  font: inherit;
  cursor: pointer;
}
.s1-editor button:disabled { opacity: 0.4; cursor: default; }
.s1-editor input, .s1-editor textarea, .s1-editor select {
  width: 100%;
  background: color-mix(in srgb, currentColor 8%, transparent);
  color: inherit;
  border: 1px solid color-mix(in srgb, currentColor 28%, transparent);
  border-radius: 4px;
  padding: 4px 6px;
  font: inherit;
}
.s1-editor textarea { resize: vertical; }
.s1-editor textarea.s1-code, .s1-editor textarea.s1-raw {
  min-height: 8em;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
}
.s1-editor .s1-field { display: flex; flex-direction: column; gap: 2px; }
.s1-editor .s1-label { opacity: 0.8; }
.s1-editor .s1-check { flex-direction: row; align-items: center; gap: 6px; }
.s1-editor .s1-check input { width: auto; }
.s1-editor .s1-row { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.s1-editor .s1-card {
  border: 1px solid color-mix(in srgb, currentColor 22%, transparent);
  border-radius: 6px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.s1-editor .s1-card .s1-card { padding: 6px; }
.s1-editor .s1-card-head { display: flex; justify-content: space-between; gap: 6px; align-items: center; }
.s1-editor .s1-card-head strong { overflow-wrap: anywhere; }
.s1-editor .s1-card-actions { display: flex; flex-wrap: wrap; gap: 4px; }
.s1-editor .s1-hint { margin: 0; opacity: 0.75; }
.s1-editor .s1-message {
  margin: 0;
  padding: 6px 8px;
  border-radius: 4px;
  border: 1px solid color-mix(in srgb, currentColor 30%, transparent);
  white-space: pre-wrap;
}
.s1-editor .s1-message.is-error { border-color: #c45; }
.s1-editor .s1-message.is-ok { border-color: #3a8; }
.s1-editor-modal {
  position: fixed;
  inset: 0;
  z-index: 100000;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
}
.s1-editor-modal-panel {
  width: min(760px, calc(100vw - 24px));
  height: min(86vh, 900px);
  background: #1b1b1b;
  color: #eee;
  border: 1px solid #666;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.s1-editor-modal-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid #444;
}
.s1-editor-modal-host { flex: 1; min-height: 0; overflow: auto; }
`;

const state = {
  node: null,
  kind: null,
  widgetName: null,
  model: null,
  raw: "",
  message: "",
  tone: "",
};

let rootEl = null;
let headerEl = null;
let messageEl = null;
let bodyEl = null;
let modalEl = null;
let sidebarReady = false;
let tabRegistered = false;
let styleInjected = false;
let escapeBound = false;

function specFor(node) {
  const name = node?.comfyClass || node?.constructor?.comfyClass || node?.type || "";
  return NODE_SPECS[name] || null;
}

function injectStyle() {
  if (styleInjected || document.getElementById("s1-editor-style")) {
    styleInjected = true;
    return;
  }
  const style = document.createElement("style");
  style.id = "s1-editor-style";
  style.textContent = CSS;
  document.head.appendChild(style);
  styleInjected = true;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function button(label, act, data = {}) {
  const node = document.createElement("button");
  node.type = "button";
  node.textContent = label;
  node.dataset.act = act;
  for (const [key, value] of Object.entries(data)) {
    if (value !== undefined && value !== null) node.dataset[key] = String(value);
  }
  return node;
}

function hint(text) {
  return el("p", "s1-hint", text);
}

function showNumber(value) {
  if (value === null || value === undefined) return "";
  return String(value);
}

function field(label, path, value, options = {}) {
  const wrap = el("label", "s1-field");
  const span = el("span", "s1-label", label);
  let input;
  if (options.check) {
    wrap.classList.add("s1-check");
    input = document.createElement("input");
    input.type = "checkbox";
    input.checked = Boolean(value);
    wrap.append(input, span);
  } else if (options.select) {
    input = document.createElement("select");
    for (const choice of options.select) {
      const option = document.createElement("option");
      option.value = choice;
      option.textContent = choice;
      input.append(option);
    }
    input.value = value ?? options.select[0];
    wrap.append(span, input);
  } else if (options.rows) {
    input = document.createElement("textarea");
    input.rows = options.rows;
    input.value = value ?? "";
    wrap.append(span, input);
  } else {
    input = document.createElement("input");
    input.type = "text";
    input.value = value ?? "";
    if (options.decimal) input.inputMode = "decimal";
    wrap.append(span, input);
  }
  input.dataset.path = path;
  input.autocomplete = "off";
  if (options.kind) input.dataset.kind = options.kind;
  if (options.rerender) input.dataset.rerender = options.rerender;
  if (options.mono || options.code) input.spellcheck = false;
  if (options.code) input.classList.add("s1-code");
  return wrap;
}

function row(left, right) {
  const node = el("div", "s1-row");
  node.append(left, right);
  return node;
}

function card(title, controls, children) {
  const box = el("section", "s1-card");
  const head = el("div", "s1-card-head");
  const bar = el("div", "s1-card-actions");
  controls.forEach((control) => bar.append(control));
  head.append(el("strong", null, title), bar);
  box.append(head);
  children.forEach((child) => box.append(child));
  return box;
}

function listButtons(listPath, index, length) {
  const up = button("Up", "up", { list: listPath, index });
  const down = button("Down", "down", { list: listPath, index });
  if (index === 0) up.disabled = true;
  if (index === length - 1) down.disabled = true;
  return [up, down, button("Remove", "remove", { list: listPath, index })];
}

function getByPath(root, path) {
  if (!path) return root;
  return path.split(".").reduce((cursor, key) => cursor?.[key], root);
}

function setPath(root, path, value) {
  const parts = path.split(".");
  let cursor = root;
  for (let index = 0; index < parts.length - 1; index += 1) cursor = cursor[parts[index]];
  cursor[parts[parts.length - 1]] = value;
}

function syncFromDom() {
  if (!rootEl) return;
  if (!state.model) {
    const raw = rootEl.querySelector("[data-raw='1']");
    if (raw) state.raw = raw.value;
    return;
  }
  rootEl.querySelectorAll("[data-path]").forEach((input) => {
    const path = input.dataset.path;
    if (input.dataset.kind === "tags" || input.dataset.kind === "ids") setPath(state.model, path, splitList(input.value));
    else if (input.type === "checkbox") setPath(state.model, path, input.checked);
    else setPath(state.model, path, input.value);
  });
}

function setMessage(text, tone) {
  state.message = text || "";
  state.tone = tone || "";
  if (!messageEl) return;
  messageEl.textContent = state.message;
  messageEl.classList.toggle("is-error", tone === "error");
  messageEl.classList.toggle("is-ok", tone === "ok");
  messageEl.hidden = !state.message;
}

function headerText() {
  if (!state.node || !state.kind) return "No node loaded";
  const spec = specFor(state.node);
  const title = state.node.title || spec?.title || state.kind;
  const id = state.node.id ?? "?";
  return `${spec?.title || state.kind} — ${title} (#${id})`;
}

function renderLoras() {
  bodyEl.append(hint("File names are typed by hand. This editor does not browse the loras/ folder."));
  state.model.loras.forEach((entry, index) => {
    const path = `loras.${index}`;
    const title = entry.lora_id ? `LoRA ${index + 1} · ${entry.lora_id}` : `LoRA ${index + 1}`;
    const box = card(title, listButtons("loras", index, state.model.loras.length), [
      field("lora_id", `${path}.lora_id`, entry.lora_id, { mono: true }),
      field("name", `${path}.name`, entry.name, { mono: true }),
      row(
        field("strength_model", `${path}.strength_model`, showNumber(entry.strength_model), { decimal: true }),
        field("strength_clip", `${path}.strength_clip`, showNumber(entry.strength_clip), { decimal: true }),
      ),
      field("tags", `${path}.tags`, (entry.tags || []).join(", "), { kind: "tags" }),
      field("enabled_default", `${path}.enabled_default`, entry.enabled_default !== false, { check: true }),
    ]);
    if (entry.meta && Object.keys(entry.meta).length) {
      box.append(hint("meta is kept on Apply and is not edited here."));
    }
    bodyEl.append(box);
  });
  bodyEl.append(button("Add LoRA", "add", { list: "loras", factory: "lora" }));
}

function renderBinding(binding, path, listPath, index, length) {
  return card(`Binding ${index + 1}`, listButtons(listPath, index, length), [
    field("lora_id", `${path}.lora_id`, binding.lora_id, { mono: true }),
    row(
      field("strength_model", `${path}.strength_model`, showNumber(binding.strength_model), { decimal: true }),
      field("strength_clip", `${path}.strength_clip`, showNumber(binding.strength_clip), { decimal: true }),
    ),
    hint("Blank strengths use the LoRA Library defaults."),
  ]);
}

function renderOption(option, path, listPath, index, length) {
  const title = option.option_id ? `Option ${index + 1} · ${option.option_id}` : `Option ${index + 1}`;
  const bindingsPath = `${path}.lora_bindings`;
  const children = [
    field("option_id", `${path}.option_id`, option.option_id, { mono: true }),
    field("label", `${path}.label`, option.label ?? ""),
    field("description", `${path}.description`, option.description ?? "", { rows: 3 }),
  ];
  (option.lora_bindings || []).forEach((binding, bindingIndex) => {
    children.push(renderBinding(binding, `${bindingsPath}.${bindingIndex}`, bindingsPath, bindingIndex, option.lora_bindings.length));
  });
  children.push(button("Add binding", "add", { list: bindingsPath, factory: "binding" }));
  return card(title, listButtons(listPath, index, length), children);
}

function renderThemes() {
  bodyEl.append(hint("Bindings store lora_id only. single asks choice; multi asks one noul per option."));
  state.model.themes.forEach((theme, index) => {
    const path = `themes.${index}`;
    const title = theme.theme_id ? `Theme ${index + 1} · ${theme.theme_id}` : `Theme ${index + 1}`;
    const optionsPath = `${path}.options`;
    const children = [
      field("theme_id", `${path}.theme_id`, theme.theme_id, { mono: true }),
      field("title", `${path}.title`, theme.title ?? ""),
      field("instructions", `${path}.instructions`, theme.instructions ?? "", { rows: 4 }),
      field("select_mode", `${path}.select_mode`, theme.select_mode || "single", { select: SELECT_MODES }),
      row(
        field("fallback_option_id", `${path}.fallback_option_id`, theme.fallback_option_id || "", { mono: true }),
        field("none_option_id", `${path}.none_option_id`, theme.none_option_id || "", { mono: true }),
      ),
      hint("Fallback and none must match an option id, or stay blank."),
    ];
    (theme.options || []).forEach((option, optionIndex) => {
      children.push(renderOption(option, `${optionsPath}.${optionIndex}`, optionsPath, optionIndex, theme.options.length));
    });
    children.push(button("Add option", "add", { list: optionsPath, factory: "option" }));
    bodyEl.append(card(title, listButtons("themes", index, state.model.themes.length), children));
  });
  bodyEl.append(button("Add theme", "add", { list: "themes", factory: "theme" }));
}

function renderAction(action, path, listPath, index, length) {
  const children = [field("type", `${path}.type`, action.type, { select: ACTION_TYPES, rerender: "type" })];
  if (action.type === "rewrite_instructions") {
    children.push(field("instructions", `${path}.instructions`, action.instructions || "", { rows: 4 }));
  } else if (action.type === "set_select_mode") {
    children.push(field("select_mode", `${path}.select_mode`, action.select_mode || "single", { select: SELECT_MODES }));
  } else if (action.type === "rewrite_options") {
    children.push(hint("JSON object: keep_option_ids, add_options, remove_option_ids, patch_bindings."));
    children.push(field("rewrite_options", `${path}.rewrite_json`, action.rewrite_json || "{}", { rows: 8, code: true }));
  }
  return card(`Action ${index + 1} · ${action.type}`, listButtons(listPath, index, length), children);
}

function renderDependency(dependency, path, listPath, index, length) {
  const when = dependency.when || { step_id: "", op: "includes_any", option_ids: [] };
  const bare = when.op === "skipped" || when.op === "answered";
  const children = [
    field("when.step_id", `${path}.when.step_id`, when.step_id || "", { mono: true }),
    field("when.op", `${path}.when.op`, when.op || "includes_any", { select: WHEN_OPS, rerender: "op" }),
  ];
  if (OP_HINT[when.op]) children.push(hint(OP_HINT[when.op]));
  if (!bare) {
    children.push(field("when.option_ids", `${path}.when.option_ids`, (when.option_ids || []).join(", "), { kind: "ids", mono: true }));
  }
  const actionsPath = `${path}.actions`;
  (dependency.actions || []).forEach((action, actionIndex) => {
    children.push(renderAction(action, `${actionsPath}.${actionIndex}`, actionsPath, actionIndex, dependency.actions.length));
  });
  children.push(button("Add action", "add", { list: actionsPath, factory: "action" }));
  return card(`Dependency ${index + 1}`, listButtons(listPath, index, length), children);
}

function renderSteps() {
  bodyEl.append(hint("Dependencies are OR. Actions in a match run in order. Nothing here calls SystemOne."));
  state.model.steps.forEach((step, index) => {
    const path = `steps.${index}`;
    const title = step.step_id ? `Step ${index + 1} · ${step.step_id}` : `Step ${index + 1}`;
    const depsPath = `${path}.dependencies`;
    const children = [
      field("step_id", `${path}.step_id`, step.step_id, { mono: true }),
      field("theme_id", `${path}.theme_id`, step.theme_id, { mono: true }),
      field("enabled_by_default", `${path}.enabled_by_default`, step.enabled_by_default !== false, { check: true }),
    ];
    (step.dependencies || []).forEach((dependency, depIndex) => {
      children.push(renderDependency(dependency, `${depsPath}.${depIndex}`, depsPath, depIndex, step.dependencies.length));
    });
    children.push(button("Add dependency", "add", { list: depsPath, factory: "dependency" }));
    bodyEl.append(card(title, listButtons("steps", index, state.model.steps.length), children));
  });
  bodyEl.append(button("Add step", "add", { list: "steps", factory: "step" }));
}

function renderRaw() {
  const area = document.createElement("textarea");
  area.className = "s1-raw";
  area.dataset.raw = "1";
  area.spellcheck = false;
  area.value = state.raw;
  bodyEl.append(
    hint("This JSON did not fit the form. Fix it here, then choose Try form. Apply writes the node only after it parses."),
    area,
    button("Try form", "try-form"),
  );
}

function renderEmpty() {
  bodyEl.append(
    hint("Click Open visual editor on a LoRA Library, Theme Library, or Theme Sequence node. This tab edits that node's JSON widget."),
  );
}

function renderBody() {
  if (!bodyEl) return;
  bodyEl.replaceChildren();
  if (!state.node || !state.kind) {
    renderEmpty();
    return;
  }
  if (!state.model) {
    renderRaw();
    return;
  }
  if (state.kind === "lora") renderLoras();
  else if (state.kind === "theme") renderThemes();
  else renderSteps();
}

function renderAll() {
  if (headerEl) headerEl.textContent = headerText();
  renderBody();
}

function findWidget(node, name) {
  return (node?.widgets || []).find((widget) => widget?.name === name) || null;
}

function widgetText(widget) {
  const value = widget?.value;
  if (typeof value === "string") return value;
  if (value == null) return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function nodeLive(node) {
  const nodes = node?.graph?._nodes;
  if (Array.isArray(nodes)) return nodes.includes(node);
  return Boolean(node);
}

function writeWidget(node, widget, text) {
  widget.value = text;
  const widgets = node.widgets || [];
  const index = widgets.indexOf(widget);
  if (Array.isArray(node.widgets_values) && index >= 0 && index < node.widgets_values.length) {
    node.widgets_values[index] = text;
  }
  if (typeof widget.callback === "function") {
    try {
      widget.callback.call(widget, text);
    } catch (exc) {
      console.warn("[S1 Editors] widget callback failed", exc);
    }
  }
  node.setDirtyCanvas?.(true, true);
  node.graph?.setDirtyCanvas?.(true, true);
  node.graph?.change?.();
  app.graph?.setDirtyCanvas?.(true, true);
  app.graph?.change?.();
  app.canvas?.setDirty?.(true, true);
}

function loadNode(node) {
  const spec = specFor(node);
  state.node = node;
  state.kind = spec?.kind || null;
  state.widgetName = spec?.widget || null;
  state.model = null;
  state.raw = "";
  if (!spec) {
    setMessage("This node has no S1 editor.", "error");
    renderAll();
    return;
  }
  const widget = findWidget(node, spec.widget);
  if (!widget) {
    setMessage(`Widget ${spec.widget} was not found on this node.`, "error");
    renderAll();
    return;
  }
  state.raw = widgetText(widget);
  const parsed = parseEditorDocument(spec.kind, state.raw);
  if (!parsed.ok) {
    setMessage(parsed.error, "error");
    renderAll();
    return;
  }
  state.model = parsed.model;
  setMessage("", "");
  renderAll();
}

function applyToNode() {
  syncFromDom();
  if (!state.node || !state.kind) {
    setMessage("Open a node first.", "error");
    return;
  }
  if (!nodeLive(state.node)) {
    setMessage("That node is no longer on the graph.", "error");
    return;
  }
  const widget = findWidget(state.node, state.widgetName);
  if (!widget) {
    setMessage(`Widget ${state.widgetName} was not found on this node.`, "error");
    return;
  }
  let model = state.model;
  if (!model) {
    const parsed = parseEditorDocument(state.kind, state.raw);
    if (!parsed.ok) {
      setMessage(parsed.error, "error");
      return;
    }
    model = parsed.model;
  }
  const result = commitModel(state.kind, model);
  if (!result.ok) {
    setMessage(result.error, "error");
    return;
  }
  writeWidget(state.node, widget, result.json);
  state.raw = result.json;
  state.model = result.model;
  setMessage("Applied to the node. Save the workflow to keep it.", "ok");
  renderAll();
}

function reloadFromNode() {
  if (!state.node) {
    setMessage("Open a node first.", "error");
    return;
  }
  if (!nodeLive(state.node)) {
    setMessage("That node is no longer on the graph.", "error");
    return;
  }
  loadNode(state.node);
  if (state.tone !== "error") setMessage("Reloaded from the node.", "ok");
}

function tryForm() {
  syncFromDom();
  const parsed = parseEditorDocument(state.kind, state.raw);
  if (!parsed.ok) {
    setMessage(parsed.error, "error");
    return;
  }
  state.model = parsed.model;
  setMessage("Loaded into the form. Apply to write it onto the node.", "ok");
  renderBody();
}

function onClick(event) {
  const target = event.target.closest("[data-act]");
  if (!target || !rootEl.contains(target)) return;
  const act = target.dataset.act;
  if (act === "apply") {
    applyToNode();
    return;
  }
  if (act === "reload") {
    reloadFromNode();
    return;
  }
  if (act === "try-form") {
    tryForm();
    return;
  }
  if (!state.model) return;
  if (act === "add") {
    syncFromDom();
    const list = getByPath(state.model, target.dataset.list);
    const factory = FACTORIES[target.dataset.factory];
    if (Array.isArray(list) && factory) list.push(factory());
    renderBody();
    return;
  }
  if (act === "remove" || act === "up" || act === "down") {
    syncFromDom();
    const list = getByPath(state.model, target.dataset.list);
    const index = Number(target.dataset.index);
    if (!Array.isArray(list) || !Number.isInteger(index)) return;
    if (act === "remove") list.splice(index, 1);
    if (act === "up" && index > 0) list.splice(index - 1, 0, list.splice(index, 1)[0]);
    if (act === "down" && index < list.length - 1) list.splice(index + 1, 0, list.splice(index, 1)[0]);
    renderBody();
  }
}

function onInput(event) {
  const input = event.target;
  if (!(input instanceof HTMLElement) || !state.model || !input.dataset.path) return;
  if (input.dataset.kind === "tags" || input.dataset.kind === "ids") setPath(state.model, input.dataset.path, splitList(input.value));
  else if (input.type === "checkbox") setPath(state.model, input.dataset.path, input.checked);
  else setPath(state.model, input.dataset.path, input.value);
  if (state.tone === "ok") setMessage("", "");
}

function onChange(event) {
  const input = event.target;
  if (!(input instanceof HTMLElement) || !state.model || !input.dataset.path) return;
  syncFromDom();
  if (input.dataset.rerender === "type") {
    const parts = input.dataset.path.split(".");
    parts.pop();
    const index = Number(parts.pop());
    const list = getByPath(state.model, parts.join("."));
    if (Array.isArray(list) && list[index]) list[index] = blankAction(list[index].type);
  }
  if (input.dataset.rerender === "op") {
    const when = getByPath(state.model, input.dataset.path.replace(/\.op$/, ""));
    if (when && (when.op === "skipped" || when.op === "answered")) when.option_ids = [];
  }
  if (input.dataset.rerender) renderBody();
}

function ensureShell() {
  injectStyle();
  if (rootEl) return rootEl;
  rootEl = el("div", "s1-editor");
  headerEl = el("h2", "s1-header", "No node loaded");
  const toolbar = el("div", "s1-toolbar");
  const apply = button("Apply to node", "apply");
  apply.title = "Write pretty JSON into the node widget";
  const reload = button("Reload from node", "reload");
  reload.title = "Replace the form with the widget text";
  toolbar.append(apply, reload);
  messageEl = el("p", "s1-message");
  messageEl.hidden = true;
  bodyEl = el("div", "s1-body");
  rootEl.append(headerEl, toolbar, hint("Apply writes the JSON widget. Typing alone does not."), messageEl, bodyEl);
  rootEl.addEventListener("click", onClick);
  rootEl.addEventListener("input", onInput);
  rootEl.addEventListener("change", onChange);
  if (!escapeBound) {
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && modalEl?.isConnected) closeModal();
    });
    escapeBound = true;
  }
  renderAll();
  return rootEl;
}

function closeModal() {
  if (modalEl?.isConnected) modalEl.remove();
}

function openModal() {
  ensureShell();
  if (!modalEl) {
    modalEl = el("div", "s1-editor-modal");
    const panel = el("div", "s1-editor-modal-panel");
    const bar = el("div", "s1-editor-modal-bar");
    const close = document.createElement("button");
    close.type = "button";
    close.textContent = "Close";
    close.addEventListener("click", () => closeModal());
    bar.append(el("strong", null, "S1 Editors"), close);
    const host = el("div", "s1-editor-modal-host");
    panel.append(bar, host);
    modalEl.append(panel);
    modalEl.addEventListener("click", (event) => {
      if (event.target === modalEl) closeModal();
    });
  }
  modalEl.querySelector(".s1-editor-modal-host").appendChild(rootEl);
  if (!modalEl.isConnected) document.body.appendChild(modalEl);
}

async function focusSidebar() {
  const command = app.extensionManager?.command;
  if (!command || typeof command.execute !== "function") return false;
  const list = Array.isArray(command.commands) ? command.commands : [];
  const match = list.find((item) => typeof item?.id === "string" && item.id.endsWith(TAB_ID) && /sidebar/i.test(item.id));
  if (!match) return false;
  let active = false;
  try {
    active = typeof match.active === "function" ? !!match.active() : false;
  } catch {
    active = false;
  }
  if (!active) {
    try {
      await command.execute(match.id);
    } catch (exc) {
      console.warn("[S1 Editors] could not focus the sidebar tab", exc);
      return false;
    }
  }
  return true;
}

function clickSidebarButton() {
  const nodes = document.querySelectorAll("button, [role='tab'], [role='button']");
  for (const node of nodes) {
    const blob = [node.getAttribute("aria-label"), node.getAttribute("title"), node.getAttribute("data-id"), node.id, node.textContent].join(" ");
    if (blob.includes("S1 Editors") || blob.includes(TAB_ID)) {
      node.click();
      return true;
    }
  }
  return false;
}

function editorVisible() {
  return Boolean(rootEl?.isConnected && rootEl.getClientRects().length > 0);
}

async function openSurface() {
  if (!sidebarReady) {
    openModal();
    return;
  }
  if (editorVisible()) return;
  if (!(await focusSidebar())) clickSidebarButton();
  window.setTimeout(() => {
    if (!editorVisible()) openModal();
  }, 120);
}

function selectNode(node) {
  const canvas = app.canvas || node?.graph?.list_of_graphcanvas?.[0];
  if (typeof canvas?.selectNode === "function") canvas.selectNode(node);
  else if (typeof canvas?.select === "function") {
    canvas.deselectAll?.();
    canvas.select(node);
  } else if (node) node.selected = true;
  canvas?.setDirty?.(true, true);
}

async function openEditorForNode(node) {
  ensureShell();
  selectNode(node);
  // The button always loads the widget, so the form matches the node.
  loadNode(node);
  await openSurface();
}

function fitNode(node) {
  try {
    if (typeof node.computeSize !== "function" || typeof node.setSize !== "function") return;
    const computed = node.computeSize();
    const width = Math.max(node.size?.[0] || 0, computed?.[0] || 0);
    const height = Math.max(node.size?.[1] || 0, computed?.[1] || 0);
    if (width && height) node.setSize([width, height]);
  } catch (exc) {
    console.warn("[S1 Editors] could not resize the node for the editor button", exc);
  }
}

function attachButton(node) {
  if (!specFor(node) || typeof node.addWidget !== "function") return;
  const existing = node.widgets || [];
  if (existing.some((widget) => widget?.name === BUTTON_NAME || widget?.label === BUTTON_LABEL)) return;
  let widget = null;
  try {
    widget = node.addWidget("button", BUTTON_NAME, BUTTON_LABEL, () => {
      void openEditorForNode(node);
    }, { serialize: false });
  } catch (exc) {
    console.warn("[S1 Editors] could not add the Open visual editor button", exc);
    return;
  }
  const created = widget || node.widgets?.[node.widgets.length - 1];
  if (!created) return;
  created.serialize = false;
  created.label = BUTTON_LABEL;
  created.options = { ...(created.options || {}), serialize: false };
  fitNode(node);
}

app.registerExtension({
  name: "SystemOne.LoraRouter.UI",
  async setup() {
    ensureShell();
    const register = app.extensionManager?.registerSidebarTab;
    if (typeof register !== "function" || tabRegistered) return;
    tabRegistered = true;
    try {
      register.call(app.extensionManager, {
        id: TAB_ID,
        icon: "pi pi-list",
        title: "S1 Editors",
        tooltip: "S1 Editors",
        type: "custom",
        render(container) {
          ensureShell();
          if (rootEl.parentElement !== container) container.appendChild(rootEl);
          closeModal();
        },
      });
      sidebarReady = true;
    } catch (exc) {
      sidebarReady = false;
      console.warn("[S1 Editors] sidebar tab was not registered", exc);
    }
  },
  nodeCreated(node) {
    attachButton(node);
  },
  getNodeMenuItems(node) {
    if (!specFor(node)) return;
    return [{ content: "Open visual editor", callback: () => { void openEditorForNode(node); } }];
  },
});
