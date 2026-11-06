// Visual editor modal for LoRA Library and Theme.
// ComfyUI loads this module because __init__.py exports WEB_DIRECTORY = "./js".
// The modal edits the node widgets. Invalid drafts are not written.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import {
  ENABLE_MATCH,
  ENABLE_OPS,
  RUN_MODES,
  SELECT_MODES,
  assignLoraIds,
  assignThemeDocument,
  blankClause,
  blankLora,
  blankOption,
  commitModel,
  fieldPathsFromError,
  loraNamesFromInfo,
  loraNamesFromModels,
  parseEditorDocument,
  splitList,
} from "./s1_model.js";

const BUTTON_NAME = "Open visual editor";
const BUTTON_LABEL = "Open visual editor";

const NODE_SPECS = {
  S1LoraLibrary: { kind: "lora", widget: "library_json", title: "LoRA Library" },
  S1Theme: {
    kind: "theme",
    widget: "theme_json",
    title: "Theme",
    prompts: true,
    enableWidget: "enable_json",
    runWidget: "run",
  },
};

const FACTORIES = {
  lora: blankLora,
  option: blankOption,
  clause: blankClause,
};

const OP_HINT = {
  eq: "Upstream selection equals this one option id.",
  neq: "Upstream answered and the selection is not this one option id. A skip does not match.",
  includes_any: "Upstream selection intersects these option ids.",
  includes_all: "Upstream selection contains every option id.",
  skipped: "That upstream theme was skipped. No option ids.",
  answered: "That upstream theme returned a selection. No option ids.",
};

const RUN_HINT = {
  disabled: "Disabled: SystemOne is not called and this theme adds no tags.",
  enabled: "Enabled: this theme always decides. Stored enable rules are ignored.",
  when_upstream: "When upstream: this theme decides only if the clauses match the upstream result.",
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
.s1-editor input[readonly] {
  cursor: default;
  border-style: dashed;
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
.s1-editor .s1-lora-picker { display: flex; flex-direction: column; gap: 4px; }
.s1-editor select.s1-lora-list { min-height: 7em; }
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
.s1-editor .s1-field.s1-invalid {
  outline: 2px solid #e23;
  border-radius: 4px;
}
.s1-editor .s1-field.s1-invalid input,
.s1-editor .s1-field.s1-invalid textarea,
.s1-editor .s1-field.s1-invalid select,
.s1-editor textarea.s1-raw.s1-invalid {
  outline: 2px solid #e23;
  border-color: #e23;
}
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

const EMPTY_LORA_HINT =
  "No LoRA files listed. Needs a running ComfyUI. The list is empty when ComfyUI is offline or models/loras has no files. Typed names still work.";

const WRITE_DELAY_MS = 220;
const POLL_MS = 500;

const state = {
  node: null,
  kind: null,
  widgetName: null,
  model: null,
  enable: null,
  raw: "",
  enableRaw: "",
  message: "",
  tone: "",
  openLoraBrowse: "",
  positive: "",
  negative: "",
  run: "disabled",
  clean: true,
  invalidPaths: [],
  writeTimer: null,
  pollTimer: null,
  writing: false,
};

let loraCatalog = { status: "idle", names: [], note: "" };
let loraCatalogToken = 0;

let rootEl = null;
let headerEl = null;
let messageEl = null;
let bodyEl = null;
let modalEl = null;
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

function readOnlyLine(label, value, markPath) {
  const wrap = el("div", "s1-field");
  if (markPath) wrap.dataset.mark = markPath;
  wrap.append(el("span", "s1-label", label));
  const input = document.createElement("input");
  input.type = "text";
  input.value = value ?? "";
  input.readOnly = true;
  input.tabIndex = -1;
  input.setAttribute("aria-readonly", "true");
  input.spellcheck = false;
  input.classList.add("s1-readonly");
  wrap.append(input);
  return wrap;
}

function displayedStrength(entry) {
  if (!entry) return "";
  const edited = Object.prototype.hasOwnProperty.call(entry, "strength");
  if (edited && entry.strength !== "" && entry.strength !== null && entry.strength !== undefined) {
    return entry.strength;
  }
  if (entry.strength_model !== undefined && entry.strength_model !== null && entry.strength_model !== "") {
    return entry.strength_model;
  }
  return "";
}

function strengthsDiffer(entry) {
  const clip = entry?.strength_clip;
  if (clip === undefined || clip === null || clip === "") return false;
  const shown = displayedStrength(entry);
  if (shown === undefined || shown === null || shown === "") return false;
  const modelValue = Number(shown);
  const clipValue = Number(clip);
  return Number.isFinite(modelValue) && Number.isFinite(clipValue) && modelValue !== clipValue;
}

function field(label, path, value, options = {}) {
  const wrap = el("label", "s1-field");
  wrap.dataset.mark = path;
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
      option.textContent = choice === "" ? "(not set)" : choice;
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
  if (options.scope) input.dataset.scope = options.scope;
  if (options.mono || options.code) input.spellcheck = false;
  if (options.code) input.classList.add("s1-code");
  return wrap;
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

function listButtons(listPath, index, length, scope) {
  const up = button("Up", "up", { list: listPath, index, scope });
  const down = button("Down", "down", { list: listPath, index, scope });
  if (index === 0) up.disabled = true;
  if (index === length - 1) down.disabled = true;
  return [up, down, button("Remove", "remove", { list: listPath, index, scope })];
}

function scopedModel(scope) {
  return scope === "enable" ? state.enable : state.model;
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

function syncPromptsFromDom() {
  if (!rootEl) return;
  rootEl.querySelectorAll("[data-prompt]").forEach((input) => {
    if (input.dataset.prompt === "positive") state.positive = input.value;
    else if (input.dataset.prompt === "negative") state.negative = input.value;
  });
  const run = rootEl.querySelector("[data-run='1']");
  if (run) state.run = run.value;
}

function syncFromDom() {
  if (!rootEl) return;
  syncPromptsFromDom();
  const raw = rootEl.querySelector("[data-raw='theme']");
  if (raw) state.raw = raw.value;
  const enableRaw = rootEl.querySelector("[data-raw='enable']");
  if (enableRaw) state.enableRaw = enableRaw.value;
  rootEl.querySelectorAll("[data-path]").forEach((input) => {
    const scope = input.dataset.scope === "enable" ? "enable" : "model";
    const root = scope === "enable" ? state.enable : state.model;
    if (!root || input.readOnly) return;
    const path = input.dataset.path;
    if (input.dataset.kind === "tags" || input.dataset.kind === "ids") setPath(root, path, splitList(input.value));
    else if (input.type === "checkbox") setPath(root, path, input.checked);
    else setPath(root, path, input.value);
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

async function readJson(route) {
  if (!api || typeof api.fetchApi !== "function") {
    throw new Error("ComfyUI api.fetchApi is missing");
  }
  const response = await api.fetchApi(route, { cache: "no-store" });
  if (!response || !response.ok) {
    throw new Error(`${route} returned ${response ? response.status : "no response"}`);
  }
  return response.json();
}

async function fetchLoraNames() {
  if (api && typeof api.getNodeDefs === "function") {
    try {
      const names = loraNamesFromInfo(await api.getNodeDefs());
      if (names) return { names, note: "" };
    } catch (exc) {
      console.warn("[S1] getNodeDefs failed", exc);
    }
  }
  for (const route of ["/object_info/LoraLoader", "/object_info/LoraLoaderModelOnly", "/object_info"]) {
    try {
      const names = loraNamesFromInfo(await readJson(route));
      if (names) return { names, note: "" };
    } catch (exc) {
      console.warn(`[S1] ${route} failed`, exc);
    }
  }
  if (api && typeof api.getModels === "function") {
    try {
      const names = loraNamesFromModels(await api.getModels("loras"));
      if (names) return { names, note: "" };
    } catch (exc) {
      console.warn("[S1] getModels(loras) failed", exc);
    }
  }
  try {
    const names = loraNamesFromModels(await readJson("/models/loras"));
    if (names) return { names, note: "" };
  } catch (exc) {
    console.warn("[S1] /models/loras failed", exc);
  }
  return { names: [], note: EMPTY_LORA_HINT };
}

function ensureLoraCatalog() {
  if (loraCatalog.status === "loading" || loraCatalog.status === "ready") return;
  const token = ++loraCatalogToken;
  loraCatalog = { status: "loading", names: [], note: "" };
  void fetchLoraNames()
    .then((result) => {
      if (token !== loraCatalogToken) return;
      const names = Array.isArray(result?.names) ? result.names : [];
      loraCatalog = { status: "ready", names, note: names.length ? "" : result?.note || EMPTY_LORA_HINT };
      if (state.kind === "lora" && bodyEl) {
        syncFromDom();
        renderBody();
      }
    })
    .catch((exc) => {
      if (token !== loraCatalogToken) return;
      console.warn("[S1] LoRA list failed", exc);
      loraCatalog = { status: "ready", names: [], note: EMPTY_LORA_HINT };
      if (state.kind === "lora" && bodyEl) {
        syncFromDom();
        renderBody();
      }
    });
}

function refreshLoraCatalog() {
  loraCatalogToken += 1;
  loraCatalog = { status: "idle", names: [], note: "" };
  ensureLoraCatalog();
}

function syncLoraDatalist() {
  try {
    if (typeof document === "undefined") return;
    let list = document.getElementById("s1-lora-names");
    if (!list) {
      list = document.createElement("datalist");
      list.id = "s1-lora-names";
      document.body.appendChild(list);
    }
    list.replaceChildren();
    const names = Array.isArray(loraCatalog.names) ? loraCatalog.names : [];
    for (const name of names) {
      const option = document.createElement("option");
      option.value = name;
      list.append(option);
    }
  } catch (exc) {
    console.warn("[S1] could not build the LoRA datalist", exc);
  }
}

function fillLoraSelect(select, names, selected) {
  select.replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Browse loras…";
  select.append(placeholder);
  for (const name of names) {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    select.append(option);
  }
  if (selected && names.includes(selected)) select.value = selected;
}

function loraPicker(path, names, selected) {
  const picker = el("div", "s1-lora-picker");
  const filter = document.createElement("input");
  filter.type = "search";
  filter.placeholder = "Filter loras…";
  filter.dataset.loraFilter = "1";
  filter.autocomplete = "off";
  filter.spellcheck = false;
  const select = document.createElement("select");
  select.className = "s1-lora-list";
  select.dataset.loraPick = path;
  select.size = 6;
  select._s1Names = names.slice();
  fillLoraSelect(select, names, selected);
  picker.append(filter, select);
  return picker;
}

function loraNameField(entryPath, value) {
  const path = `${entryPath}.name`;
  const wrap = el("div", "s1-field");
  wrap.dataset.mark = path;
  wrap.append(el("span", "s1-label", "name"));
  const input = document.createElement("input");
  input.type = "text";
  input.value = value ?? "";
  input.dataset.path = path;
  input.autocomplete = "off";
  input.spellcheck = false;
  input.setAttribute("list", "s1-lora-names");
  input.placeholder = "relative name under models/loras";
  wrap.append(input);
  const names = Array.isArray(loraCatalog.names) ? loraCatalog.names : [];
  if (!names.length) return wrap;
  const open = state.openLoraBrowse === path;
  wrap.append(button(open ? "Hide lora list" : "Browse loras…", "browse-loras", { browse: path }));
  if (open) wrap.append(loraPicker(path, names, value ?? ""));
  if (value && !names.includes(value)) {
    wrap.append(hint("This name is not in the current loras list. It is still saved as name."));
  }
  return wrap;
}

function filterLoraOptions(input) {
  const select = input.parentElement?.querySelector("select[data-lora-pick]");
  if (!select || !Array.isArray(select._s1Names)) return;
  const query = input.value.trim().toLowerCase();
  const matched = select._s1Names.filter((name) => name.toLowerCase().includes(query));
  fillLoraSelect(select, matched, select.value);
  const placeholder = select.options[0];
  if (placeholder && !placeholder.value) placeholder.textContent = query ? "Matching loras…" : "Browse loras…";
}

function applyLoraPick(select) {
  const name = select.value;
  if (!name || !state.model) return;
  const textInput = select.closest?.(".s1-field")?.querySelector("input[data-path]");
  if (textInput) textInput.value = name;
  setPath(state.model, select.dataset.loraPick, name);
  syncFromDom();
  renderBody();
  scheduleLiveWrite();
}

function renderLoras() {
  ensureLoraCatalog();
  syncLoraDatalist();
  const names = Array.isArray(loraCatalog.names) ? loraCatalog.names : [];
  bodyEl.append(
    hint("The name field stores the relative file name, the same string as the stock Lora Loader. Type it, or pick from Browse loras."),
  );
  bodyEl.append(
    hint("lora_id is assigned automatically (lora_1, lora_2, and so on) and is read-only. Existing ids are kept. One strength writes both strength_model and strength_clip."),
  );
  if (loraCatalog.status === "loading") bodyEl.append(hint("Loading the LoRA list from ComfyUI…"));
  else if (!names.length) bodyEl.append(hint(loraCatalog.note || EMPTY_LORA_HINT));
  bodyEl.append(button("Refresh loras", "refresh-loras"));
  state.model.loras.forEach((entry, index) => {
    const path = `loras.${index}`;
    const title = entry.lora_id ? `LoRA ${index + 1} · ${entry.lora_id}` : `LoRA ${index + 1}`;
    const box = card(title, listButtons("loras", index, state.model.loras.length), [
      readOnlyLine("lora_id", entry.lora_id || "", `${path}.lora_id`),
      loraNameField(path, entry.name),
      field("strength (model & clip)", `${path}.strength`, showNumber(displayedStrength(entry)), { decimal: true }),
      field("tags", `${path}.tags`, (entry.tags || []).join(", "), { kind: "tags" }),
      field("enabled_default", `${path}.enabled_default`, entry.enabled_default !== false, { check: true }),
    ]);
    if (strengthsDiffer(entry)) {
      box.append(hint("strength_clip differs. The next valid write copies this strength to both strength_model and strength_clip."));
    }
    if (entry.meta && Object.keys(entry.meta).length) {
      box.append(hint("meta is kept when a valid edit is written, and the form does not edit it."));
    }
    bodyEl.append(box);
  });
  bodyEl.append(button("Add LoRA", "add", { list: "loras", factory: "lora" }));
}

function noneField(theme) {
  const ids = [];
  for (const option of theme.options || []) {
    if (option?.option_id && !ids.includes(option.option_id)) ids.push(option.option_id);
  }
  const current = theme.none_option_id || "";
  const choices = [""].concat(ids);
  if (current && !choices.includes(current)) choices.push(current);
  return field("none_option_id", "none_option_id", current, { select: choices });
}

function renderOption(option, index, length) {
  const path = `options.${index}`;
  const title = option.option_id ? `Option ${index + 1} · ${option.option_id}` : `Option ${index + 1}`;
  return card(title, listButtons("options", index, length), [
    readOnlyLine("option_id", option.option_id || "", `${path}.option_id`),
    field("label", `${path}.label`, option.label ?? ""),
    field("description", `${path}.description`, option.description ?? "", { rows: 3 }),
    field("tags", `${path}.tags`, (option.tags || []).join(", "), { kind: "tags" }),
    hint("Selected options contribute these tags. The none option contributes none."),
  ]);
}

function renderThemeFields() {
  const theme = state.model;
  bodyEl.append(
    hint(
      "theme_id and option_id are assigned automatically (theme_1, option_1, and so on) and are read-only. Existing ids are kept, including manual ids.",
    ),
  );
  bodyEl.append(
    hint(
      "This form cannot see other Theme nodes. If a chain repeats theme_id, set a unique id in the JSON widget once; this form keeps it.",
    ),
  );
  const children = [
    readOnlyLine("theme_id", theme.theme_id || "", "theme_id"),
    field("title", "title", theme.title ?? ""),
    field("instructions", "instructions", theme.instructions ?? "", { rows: 4 }),
    field("select_mode", "select_mode", theme.select_mode || "single", { select: SELECT_MODES }),
    noneField(theme),
    hint("none must match an option id in this theme, or stay unset. There is no fallback option."),
  ];
  (theme.options || []).forEach((option, index) => {
    children.push(renderOption(option, index, theme.options.length));
  });
  children.push(button("Add option", "add", { list: "options", factory: "option" }));
  const title = theme.theme_id ? `Theme · ${theme.theme_id}` : "Theme";
  bodyEl.append(card(title, [], children));
}

function renderClause(clause, index, length) {
  const path = `clauses.${index}`;
  const bare = clause.op === "skipped" || clause.op === "answered";
  const children = [
    field("upstream theme_id", `${path}.theme_id`, clause.theme_id || "", { mono: true, scope: "enable" }),
    field("op", `${path}.op`, clause.op || "includes_any", {
      select: ENABLE_OPS,
      rerender: "op",
      scope: "enable",
    }),
  ];
  if (OP_HINT[clause.op]) children.push(hint(OP_HINT[clause.op]));
  if (!bare) {
    children.push(
      field("option_ids", `${path}.option_ids`, (clause.option_ids || []).join(", "), {
        kind: "ids",
        mono: true,
        scope: "enable",
      }),
    );
  }
  return card(`Clause ${index + 1}`, listButtons("clauses", index, length, "enable"), children);
}

function renderEnableFields() {
  const enable = state.enable;
  const box = el("section", "s1-card");
  box.append(el("h3", null, "Enable when upstream"));
  box.append(
    hint(
      "Clauses name an upstream theme_id and its option ids. match any is OR. match all is AND. An empty list matches nothing.",
    ),
  );
  box.append(field("match", "match", enable.match || "any", { select: ENABLE_MATCH, scope: "enable" }));
  (enable.clauses || []).forEach((clause, index) => {
    box.append(renderClause(clause, index, enable.clauses.length));
  });
  box.append(button("Add clause", "add", { list: "clauses", factory: "clause", scope: "enable" }));
  bodyEl.append(box);
}

function promptField(name, label, value) {
  const wrap = el("label", "s1-field");
  wrap.append(el("span", "s1-label", label));
  const area = document.createElement("textarea");
  area.rows = 4;
  area.value = value ?? "";
  area.dataset.prompt = name;
  wrap.append(area);
  return wrap;
}

function renderPrompts() {
  const box = el("section", "s1-card");
  box.append(el("h3", null, "Prompts"));
  box.append(
    hint("Positive, then negative. A valid edit writes these widgets with theme_json. They are not stored inside theme_json."),
  );
  box.append(promptField("positive", "Positive prompt", state.positive));
  box.append(promptField("negative", "Negative prompt", state.negative));
  bodyEl.append(box);
}

function renderRun() {
  const box = el("section", "s1-card");
  box.append(el("h3", null, "Run"));
  const wrap = el("label", "s1-field");
  wrap.dataset.mark = "run";
  wrap.append(el("span", "s1-label", "run"));
  const select = document.createElement("select");
  select.dataset.run = "1";
  for (const choice of RUN_MODES) {
    const option = document.createElement("option");
    option.value = choice;
    option.textContent = choice;
    select.append(option);
  }
  select.value = RUN_MODES.includes(state.run) ? state.run : "disabled";
  wrap.append(select);
  box.append(wrap);
  box.append(hint(RUN_HINT[select.value] || RUN_HINT.disabled));
  bodyEl.append(box);
}

function renderRaw(which, text, blurb) {
  const area = document.createElement("textarea");
  area.className = "s1-raw";
  area.dataset.raw = which;
  area.spellcheck = false;
  area.value = text ?? "";
  bodyEl.append(hint(blurb), area, button("Try form", "try-form"));
}

function renderEmpty() {
  bodyEl.append(hint("Open visual editor on a LoRA Library or Theme node. This modal edits that node's JSON widgets."));
}

function renderBody() {
  if (!bodyEl) return;
  bodyEl.replaceChildren();
  if (!state.node || !state.kind) {
    renderEmpty();
    applyInvalidMarks();
    return;
  }
  if (state.kind === "theme") {
    renderPrompts();
    renderRun();
  }
  if (!state.model) {
    renderRaw(
      "theme",
      state.raw,
      "This JSON did not fit the form. Fix it here, then choose Try form. A successful parse writes the node. Invalid JSON stays here and is not written.",
    );
    applyInvalidMarks();
    return;
  }
  if (state.kind === "lora") renderLoras();
  else {
    renderThemeFields();
    if (!state.enable) {
      renderRaw(
        "enable",
        state.enableRaw,
        "enable_json did not fit the form. Invalid enable JSON is not written, and theme_json is left unchanged too.",
      );
    } else renderEnableFields();
  }
  applyInvalidMarks();
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
      console.warn("[S1] widget callback failed", exc);
    }
  }
  node.setDirtyCanvas?.(true, true);
  node.graph?.setDirtyCanvas?.(true, true);
  node.graph?.change?.();
  app.graph?.setDirtyCanvas?.(true, true);
  app.graph?.change?.();
  app.canvas?.setDirty?.(true, true);
}

function writeNamed(node, name, text) {
  const widget = findWidget(node, name);
  if (!widget) return false;
  if (widgetText(widget) !== text) writeWidget(node, widget, text);
  return true;
}

function loadNode(node) {
  flushLiveWrite();
  const spec = specFor(node);
  state.node = node;
  state.kind = spec?.kind || null;
  state.widgetName = spec?.widget || null;
  state.model = null;
  state.enable = null;
  state.raw = "";
  state.enableRaw = "";
  state.openLoraBrowse = "";
  state.positive = "";
  state.negative = "";
  state.run = "disabled";
  state.clean = false;
  state.invalidPaths = [];
  if (!spec) {
    setMessage("This node has no visual editor.", "error");
    renderAll();
    return;
  }
  if (spec.prompts) {
    state.positive = widgetText(findWidget(node, "positive"));
    state.negative = widgetText(findWidget(node, "negative"));
    state.run = widgetText(findWidget(node, spec.runWidget)) || "disabled";
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
    state.clean = false;
    state.invalidPaths = ["__raw__"].concat(fieldPathsFromError(parsed.error));
    setMessage(parsed.error, "error");
    renderAll();
    return;
  }
  state.model = parsed.model;
  if (spec.kind === "theme") {
    const enableWidget = findWidget(node, spec.enableWidget);
    state.enableRaw = enableWidget ? widgetText(enableWidget) : "";
    const enableParsed = parseEditorDocument("enable", state.enableRaw);
    if (!enableParsed.ok) {
      state.enable = null;
      state.clean = false;
      state.invalidPaths = ["__enable_raw__"].concat(fieldPathsFromError(enableParsed.error));
      setMessage(enableParsed.error, "error");
      renderAll();
      return;
    }
    state.enable = enableParsed.model;
  }
  state.clean = true;
  state.invalidPaths = [];
  setMessage("", "");
  renderAll();
}

function idSignature() {
  const model = state.model;
  if (!model) return "";
  const loras = (model.loras || []).map((entry) => entry?.lora_id || "");
  const options = (model.options || []).map((option) => option?.option_id || "");
  return JSON.stringify({ loras, theme: model.theme_id || "", options });
}

function applyInvalidMarks() {
  if (!rootEl) return;
  const marks = new Set(state.invalidPaths || []);
  rootEl.querySelectorAll(".s1-field").forEach((wrap) => {
    const input = wrap.querySelector("[data-path]");
    const path = wrap.dataset.mark || (input ? input.dataset.path : "");
    wrap.classList.toggle("s1-invalid", Boolean(path) && marks.has(path));
  });
  rootEl.querySelectorAll("textarea.s1-raw").forEach((area) => {
    const which = area.dataset.raw === "enable" ? "__enable_raw__" : "__raw__";
    area.classList.toggle("s1-invalid", marks.has(which));
  });
}

function cancelLiveWrite() {
  if (!state.writeTimer) return;
  clearTimeout(state.writeTimer);
  state.writeTimer = null;
}

function scheduleLiveWrite() {
  state.clean = false;
  cancelLiveWrite();
  state.writeTimer = window.setTimeout(() => {
    state.writeTimer = null;
    liveWrite();
  }, WRITE_DELAY_MS);
}

function flushLiveWrite() {
  if (!state.writeTimer) return;
  cancelLiveWrite();
  liveWrite();
}

function rejectDraft(error, marks) {
  state.clean = false;
  state.invalidPaths = marks;
  setMessage(error, "error");
  applyInvalidMarks();
}

function liveWrite() {
  if (!state.node || !state.kind) return;
  if (!nodeLive(state.node)) {
    state.clean = false;
    setMessage("That node is no longer on the graph.", "error");
    return;
  }
  const widget = findWidget(state.node, state.widgetName);
  if (!widget) {
    state.clean = false;
    setMessage(`Widget ${state.widgetName} was not found on this node.`, "error");
    return;
  }
  syncFromDom();
  const hadModel = Boolean(state.model);
  if (!state.model) {
    const parsed = parseEditorDocument(state.kind, state.raw);
    if (!parsed.ok) {
      rejectDraft(parsed.error, ["__raw__"].concat(fieldPathsFromError(parsed.error)));
      return;
    }
    state.model = parsed.model;
  }
  if (state.kind === "theme" && !state.enable) {
    const parsed = parseEditorDocument("enable", state.enableRaw);
    if (!parsed.ok) {
      rejectDraft(parsed.error, ["__enable_raw__"].concat(fieldPathsFromError(parsed.error)));
      return;
    }
    state.enable = parsed.model;
  }
  const beforeIds = idSignature();
  const result = commitModel(state.kind, state.model);
  if (!result.ok) {
    state.clean = false;
    state.invalidPaths = fieldPathsFromError(result.error);
    setMessage(result.error, "error");
    if (idSignature() !== beforeIds) {
      renderAll();
      return;
    }
    applyInvalidMarks();
    return;
  }
  let enableResult = null;
  if (state.kind === "theme") {
    enableResult = commitModel("enable", state.enable);
    if (!enableResult.ok) {
      state.clean = false;
      state.invalidPaths = fieldPathsFromError(enableResult.error);
      setMessage(enableResult.error, "error");
      applyInvalidMarks();
      return;
    }
  }
  state.invalidPaths = [];
  state.writing = true;
  try {
    if (widgetText(widget) !== result.json) writeWidget(state.node, widget, result.json);
    if (state.kind === "theme") {
      const spec = specFor(state.node);
      writeNamed(state.node, spec.enableWidget, enableResult.json);
      writeNamed(state.node, "positive", state.positive ?? "");
      writeNamed(state.node, "negative", state.negative ?? "");
      writeNamed(state.node, spec.runWidget, state.run || "disabled");
    }
  } finally {
    state.writing = false;
  }
  state.raw = result.json;
  if (enableResult) state.enableRaw = enableResult.json;
  state.clean = true;
  const idsChanged = idSignature() !== beforeIds;
  state.model = result.model;
  if (enableResult) state.enable = enableResult.model;
  setMessage("", "");
  if (!hadModel || idsChanged) {
    renderAll();
    return;
  }
  applyInvalidMarks();
}

function pollWidgets() {
  if (state.writing || state.writeTimer || !state.clean) return;
  if (!editorVisible()) return;
  if (!state.node || !state.kind || !nodeLive(state.node)) return;
  const widget = findWidget(state.node, state.widgetName);
  if (!widget) return;
  const text = widgetText(widget);
  let extra = false;
  if (state.kind === "theme") {
    const spec = specFor(state.node);
    const enableText = widgetText(findWidget(state.node, spec.enableWidget));
    const positive = widgetText(findWidget(state.node, "positive"));
    const negative = widgetText(findWidget(state.node, "negative"));
    const run = widgetText(findWidget(state.node, spec.runWidget));
    extra = enableText !== state.enableRaw || positive !== state.positive || negative !== state.negative || run !== state.run;
  }
  if (text !== state.raw || extra) loadNode(state.node);
}

function ensurePoll() {
  if (state.pollTimer || typeof window === "undefined") return;
  state.pollTimer = window.setInterval(pollWidgets, POLL_MS);
}

function tryForm() {
  cancelLiveWrite();
  syncFromDom();
  liveWrite();
}

function onClick(event) {
  const target = event.target.closest("[data-act]");
  if (!target || !rootEl.contains(target)) return;
  const act = target.dataset.act;
  if (act === "try-form") {
    tryForm();
    return;
  }
  if (act === "refresh-loras") {
    if (state.model) syncFromDom();
    refreshLoraCatalog();
    renderBody();
    scheduleLiveWrite();
    return;
  }
  const scope = target.dataset.scope === "enable" ? "enable" : "model";
  const root = scopedModel(scope);
  if (!root) return;
  if (act === "browse-loras") {
    syncFromDom();
    const path = target.dataset.browse || "";
    state.openLoraBrowse = state.openLoraBrowse === path ? "" : path;
    renderBody();
    return;
  }
  if (act === "add") {
    syncFromDom();
    const list = getByPath(root, target.dataset.list);
    const factory = FACTORIES[target.dataset.factory];
    if (Array.isArray(list) && factory) {
      list.push(factory());
      if (state.kind === "lora") assignLoraIds(state.model);
      if (state.kind === "theme" && scope === "model") assignThemeDocument(state.model);
    }
    renderBody();
    scheduleLiveWrite();
    return;
  }
  if (act === "remove" || act === "up" || act === "down") {
    syncFromDom();
    const list = getByPath(root, target.dataset.list);
    const index = Number(target.dataset.index);
    if (!Array.isArray(list) || !Number.isInteger(index)) return;
    if (act === "remove") list.splice(index, 1);
    if (act === "up" && index > 0) list.splice(index - 1, 0, list.splice(index, 1)[0]);
    if (act === "down" && index < list.length - 1) list.splice(index + 1, 0, list.splice(index, 1)[0]);
    if (state.kind === "lora") assignLoraIds(state.model);
    if (state.kind === "theme" && scope === "model") assignThemeDocument(state.model);
    renderBody();
    scheduleLiveWrite();
  }
}

function onInput(event) {
  const input = event.target;
  if (!(input instanceof HTMLElement)) return;
  if (input.dataset.loraFilter != null) {
    filterLoraOptions(input);
    return;
  }
  if (input.dataset.raw != null) {
    if (input.dataset.raw === "enable") state.enableRaw = input.value;
    else state.raw = input.value;
    if (input.dataset.raw === "theme") state.model = null;
    if (input.dataset.raw === "enable") state.enable = null;
    scheduleLiveWrite();
    return;
  }
  if (input.dataset.prompt === "positive" || input.dataset.prompt === "negative") {
    state[input.dataset.prompt] = input.value;
    scheduleLiveWrite();
    return;
  }
  if (input.dataset.run != null) {
    state.run = input.value;
    scheduleLiveWrite();
    return;
  }
  const root = input.dataset.scope === "enable" ? state.enable : state.model;
  if (!root || !input.dataset.path || input.readOnly) return;
  if (input.dataset.kind === "tags" || input.dataset.kind === "ids") setPath(root, input.dataset.path, splitList(input.value));
  else if (input.type === "checkbox") setPath(root, input.dataset.path, input.checked);
  else setPath(root, input.dataset.path, input.value);
  scheduleLiveWrite();
}

function onChange(event) {
  const input = event.target;
  if (!(input instanceof HTMLElement)) return;
  if (input.dataset.loraPick) {
    applyLoraPick(input);
    return;
  }
  if (input.dataset.raw != null) {
    if (input.dataset.raw === "enable") state.enableRaw = input.value;
    else {
      state.raw = input.value;
      state.model = null;
    }
    scheduleLiveWrite();
    return;
  }
  if (input.dataset.prompt === "positive" || input.dataset.prompt === "negative") {
    state[input.dataset.prompt] = input.value;
    scheduleLiveWrite();
    return;
  }
  if (input.dataset.run != null) {
    state.run = input.value;
    renderBody();
    scheduleLiveWrite();
    return;
  }
  const root = input.dataset.scope === "enable" ? state.enable : state.model;
  if (!root || !input.dataset.path || input.readOnly) return;
  syncFromDom();
  if (input.dataset.rerender === "op") {
    const clause = getByPath(state.enable, input.dataset.path.replace(/\.op$/, ""));
    if (clause && (clause.op === "skipped" || clause.op === "answered")) clause.option_ids = [];
  }
  if (input.dataset.rerender) renderBody();
  scheduleLiveWrite();
}

function ensureShell() {
  injectStyle();
  if (rootEl) return rootEl;
  rootEl = el("div", "s1-editor");
  headerEl = el("h2", "s1-header", "No node loaded");
  messageEl = el("p", "s1-message");
  messageEl.hidden = true;
  bodyEl = el("div", "s1-body");
  rootEl.append(
    headerEl,
    hint("Valid edits are written to the node. Invalid fields stay in the editor and show a red outline."),
    messageEl,
    bodyEl,
  );
  rootEl.addEventListener("click", onClick);
  rootEl.addEventListener("input", onInput);
  rootEl.addEventListener("change", onChange);
  ensurePoll();
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
    bar.append(el("strong", null, "Visual editor"), close);
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

function editorVisible() {
  return Boolean(rootEl?.isConnected && rootEl.getClientRects().length > 0);
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

function openEditorForNode(node) {
  ensureShell();
  selectNode(node);
  loadNode(node);
  openModal();
}

function fitNode(node) {
  try {
    if (typeof node.computeSize !== "function" || typeof node.setSize !== "function") return;
    const computed = node.computeSize();
    const width = Math.max(node.size?.[0] || 0, computed?.[0] || 0);
    const height = Math.max(node.size?.[1] || 0, computed?.[1] || 0);
    if (width && height) node.setSize([width, height]);
  } catch (exc) {
    console.warn("[S1] could not resize the node for the editor button", exc);
  }
}

function attachButton(node) {
  if (!specFor(node) || typeof node.addWidget !== "function") return;
  const existing = node.widgets || [];
  if (existing.some((widget) => widget?.name === BUTTON_NAME || widget?.label === BUTTON_LABEL)) return;
  let widget = null;
  try {
    widget = node.addWidget("button", BUTTON_NAME, BUTTON_LABEL, () => {
      openEditorForNode(node);
    }, { serialize: false });
  } catch (exc) {
    console.warn("[S1] could not add the Open visual editor button", exc);
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
  },
  nodeCreated(node) {
    attachButton(node);
  },
  getNodeMenuItems(node) {
    if (!specFor(node)) return;
    return [{ content: "Open visual editor", callback: () => { openEditorForNode(node); } }];
  },
});
