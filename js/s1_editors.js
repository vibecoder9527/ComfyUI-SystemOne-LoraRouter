// Visual editor modal for LoRA Library, Theme Root, and Theme.
// ComfyUI loads this module because __init__.py exports WEB_DIRECTORY = "./js".
// The modal edits theme_json or library_json. Invalid drafts are not written.
// Prompts are sockets. Positive is the input above negative. Negative is optional. Prompts are not stored in theme_json.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import {
  SELECT_MODES,
  assignLoraIds,
  assignThemeDocument,
  planOptionOutputs,
  planThemeIds,
  relinkOptionSlots,
  orderThemePromptInputs,
  blankLora,
  blankOption,
  commitModel,
  fieldPathsFromError,
  loraNamesFromInfo,
  loraNamesFromModels,
  parseEditorDocument,
  splitList,
  ensureDefaultNoneOption,
  isNoneLikeOption,
  DEFAULT_NONE_LABEL,
  collectGraphTags,
  syncCollectInputs,
} from "./s1_model.js";

const BUTTON_NAME = "Open visual editor";
const BUTTON_LABEL = "Open visual editor";

const NODE_SPECS = {
  S1LoraLibrary: { kind: "lora", widget: "library_json", title: "LoRA Library" },
  S1ThemeRoot: { kind: "theme", widget: "theme_json", title: "Theme Root" },
  S1Theme: { kind: "theme", widget: "theme_json", title: "Theme" },
};

const FACTORIES = {
  lora: blankLora,
  option: blankOption,
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
.s1-editor .s1-lora-row,
.s1-editor .s1-option-row {
  display: grid;
  grid-template-columns: auto minmax(8em, 1.4fr) 5.5em minmax(7em, 1fr) auto;
  gap: 6px;
  align-items: end;
}
.s1-editor .s1-lora-row .s1-check { margin: 0; }
.s1-editor .s1-lora-row .s1-field,
.s1-editor .s1-option-row .s1-field { min-width: 0; }
.s1-editor .s1-lora-row input[type="checkbox"] { width: auto; }
.s1-editor .s1-strength { max-width: 6em; }
@media (max-width: 700px) {
  .s1-editor .s1-lora-row,
  .s1-editor .s1-option-row {
    grid-template-columns: auto 1fr;
  }
}
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
  raw: "",
  message: "",
  tone: "",
  openLoraBrowse: "",
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

function scopedModel() {
  return state.model;
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
  const raw = rootEl.querySelector("[data-raw='theme']");
  if (raw) state.raw = raw.value;
  rootEl.querySelectorAll("[data-path]").forEach((input) => {
    const root = state.model;
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
    const row = el("div", "s1-lora-row");
    row.append(
      field("On", `${path}.enabled_default`, entry.enabled_default !== false, { check: true }),
      loraNameField(path, entry.name),
      field("strength", `${path}.strength`, showNumber(displayedStrength(entry)), { decimal: true }),
      tagField(`${path}.tags`, (entry.tags || []).join(", ")),
      el("div", "s1-card-actions"),
    );
    const actions = row.querySelector(".s1-card-actions");
    listButtons("loras", index, state.model.loras.length).forEach((btn) => actions.append(btn));
    const box = card(title, [], [row]);
    box.append(hint("On: always apply. Off: apply only when a selected tag overlaps. Strength writes both strength_model and strength_clip."));
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

function tagField(path, value) {
  const wrap = field("tags", path, value, { kind: "tags" });
  const input = wrap.querySelector("input, textarea");
  if (input) {
    const listId = `s1-tags-${path.replace(/[^A-Za-z0-9_-]/g, "-")}`;
    input.setAttribute("list", listId);
    const list = document.createElement("datalist");
    list.id = listId;
    const tags = collectGraphTags(state.node?.graph, state.node);
    for (const tag of tags) {
      const option = document.createElement("option");
      option.value = tag;
      list.append(option);
    }
    wrap.append(list);
  }
  return wrap;
}

function noneField(theme) {
  // none_option_id is assigned automatically and is not a form field.
  // The default 以上皆非 row is rendered as a locked option instead.
  return hint(`The last option is ${DEFAULT_NONE_LABEL}. It is selectable, has its own output slot, and contributes no tags.`);
}

function renderOption(option, index, length) {
  const path = `options.${index}`;
  const locked = Boolean(option?.option_id && option.option_id === state.model?.none_option_id) || isNoneLikeOption(option);
  const title = option.option_id
    ? (locked ? `${DEFAULT_NONE_LABEL} · ${option.option_id}` : `Option ${index + 1} · ${option.option_id}`)
    : `Option ${index + 1}`;
  const controls = locked ? [] : listButtons("options", index, length);
  const fields = [
    field("label", `${path}.label`, option.label ?? (locked ? DEFAULT_NONE_LABEL : "")),
    field("description", `${path}.description`, option.description ?? "", { rows: 2 }),
  ];
  if (locked) {
    fields.push(hint("This is the default none-of-the-above choice. It always has an output slot and contributes no tags."));
  } else {
    fields.push(tagField(`${path}.tags`, (option.tags || []).join(", ")));
  }
  return card(title, controls, fields);
}

function renderThemeFields() {
  const theme = state.model;
  bodyEl.append(
    hint(
      "theme_id and option_id are assigned automatically and shown in the card titles. They are not form fields. New and duplicated themes receive the next free theme_N on the graph before queue. A saved non-empty id stays when it does not collide. Existing option ids are kept. Decision sources still use those ids.",
    ),
  );
  bodyEl.append(
    hint(
      "Positive is the input above negative. Negative is optional; unconnected or blank is sent as empty. Prompts are not stored in theme_json. Wire them from prompt nodes. This editor writes theme_json only. Option order is output-slot order.",
    ),
  );
  bodyEl.append(
    hint(
      "A loaded workflow that repeats a theme_id keeps both saved documents and shows a theme_id conflict. A decision chain still rejects a repeated theme_id.",
    ),
  );
  const children = [
    field("title", "title", theme.title ?? ""),
    field("instructions", "instructions", theme.instructions ?? "", { rows: 4 }),
    field("select_mode", "select_mode", theme.select_mode || "single", { select: SELECT_MODES }),
    noneField(theme),
  ];
  (theme.options || []).forEach((option, index) => {
    children.push(renderOption(option, index, theme.options.length));
  });
  children.push(button("Add option", "add", { list: "options", factory: "option" }));
  const title = theme.theme_id ? `Theme · ${theme.theme_id}` : "Theme";
  bodyEl.append(card(title, [], children));
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
  bodyEl.append(
    hint(
      "Open visual editor on a LoRA Library, Theme Root, or Theme node. This modal edits that node's JSON widget.",
    ),
  );
}

function renderBody() {
  if (!bodyEl) return;
  bodyEl.replaceChildren();
  if (!state.node || !state.kind) {
    renderEmpty();
    applyInvalidMarks();
    return;
  }
  if (!state.model) {
    renderRaw(
      "theme",
      state.raw,
      "This JSON did not fit the form. Fix it here, then choose Try form. A successful parse writes theme_json. Invalid JSON stays here and is not written.",
    );
    applyInvalidMarks();
    return;
  }
  if (state.kind === "lora") renderLoras();
  else renderThemeFields();
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
  state.raw = "";
  state.openLoraBrowse = "";
  state.clean = false;
  state.invalidPaths = [];
  if (!spec) {
    setMessage("This node has no visual editor.", "error");
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
    state.clean = false;
    state.invalidPaths = ["__raw__"].concat(fieldPathsFromError(parsed.error));
    setMessage(parsed.error, "error");
    renderAll();
    return;
  }
  state.model = parsed.model;
  if (spec.kind === "theme") {
    const before = JSON.stringify(state.model);
    assignThemeDocument(state.model);
    if (JSON.stringify(state.model) !== before) scheduleLiveWrite();
  }
  state.clean = true;
  state.invalidPaths = [];
  announceThemeConflict(node);
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
    const which = "__raw__";
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
  state.invalidPaths = [];
  state.writing = true;
  try {
    if (widgetText(widget) !== result.json) writeWidget(state.node, widget, result.json);
  } finally {
    state.writing = false;
  }
  state.raw = result.json;
  state.clean = true;
  const idsChanged = idSignature() !== beforeIds;
  state.model = result.model;
  announceThemeConflict(state.node);
  if (state.kind === "theme") syncOptionOutputs(state.node);
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
  if (text !== state.raw) loadNode(state.node);
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
  const root = scopedModel();
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
      const noneIndex = list.findIndex((item) => item && (item.option_id === state.model?.none_option_id || isNoneLikeOption(item)));
      if (target.dataset.list === "options" && noneIndex >= 0) list.splice(noneIndex, 0, factory());
      else list.push(factory());
      if (state.kind === "lora") assignLoraIds(state.model);
      if (state.kind === "theme") assignThemeDocument(state.model);
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
    if (act === "remove") {
      const item = list[index];
      if (item && (item.option_id === state.model?.none_option_id || isNoneLikeOption(item))) return;
      list.splice(index, 1);
    }
    if (act === "up" && index > 0) list.splice(index - 1, 0, list.splice(index, 1)[0]);
    if (act === "down" && index < list.length - 1) list.splice(index + 1, 0, list.splice(index, 1)[0]);
    if (state.kind === "lora") assignLoraIds(state.model);
    if (state.kind === "theme") assignThemeDocument(state.model);
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
    state.raw = input.value;
    if (input.dataset.raw === "theme") state.model = null;
    scheduleLiveWrite();
    return;
  }
  const root = state.model;
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
    state.raw = input.value;
    state.model = null;
    scheduleLiveWrite();
    return;
  }
  const root = state.model;
  if (!root || !input.dataset.path || input.readOnly) return;
  syncFromDom();
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
  if (specFor(node)?.kind === "theme") reconcileThemeIds();
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

const THEME_CONFLICT_SUFFIX = " (theme_id conflict)";

let configuringGraph = false;
let reconcilingThemes = false;
let themeReconcilePending = false;
// Nodes constructed while a workflow is loading. Their ids are stamped after
// configure(), because nodeCreated runs before the saved id and widgets land.
const restoredThisLoad = new Set();

function isThemeNode(node) {
  return specFor(node)?.kind === "theme";
}

function announceThemeConflict(node) {
  const message = node?.s1ThemeIdConflict || "";
  if (message) setMessage(message, "error");
  else setMessage("", "");
}

function themeGroups() {
  const groups = [];
  const seen = new Set();
  const visit = (graph) => {
    if (!graph || seen.has(graph)) return;
    seen.add(graph);
    const nodes = graph._nodes || graph.nodes;
    if (!Array.isArray(nodes)) return;
    groups.push(nodes.filter(isThemeNode));
    for (const node of nodes) {
      const nested = node?.subgraph;
      if (nested && nested !== graph) visit(nested);
    }
  };
  visit(app.graph);
  return groups;
}

function themeNodes() {
  return themeGroups().flat();
}

// graphToPrompt reads serializeValue when it is set, otherwise widget.value.
// Hooking the widget covers a queue path that does not call the wrapped app methods.
function installThemeSerialize(node) {
  const widget = findWidget(node, "theme_json");
  if (!widget || widget.__s1ThemeSerialize) return;
  const original = typeof widget.serializeValue === "function" ? widget.serializeValue : null;
  widget.serializeValue = function s1ThemeSerialize(...args) {
    if (!reconcilingThemes && !configuringGraph) reconcileThemeIds();
    if (original) return original.apply(this, args);
    return this.value;
  };
  widget.__s1ThemeSerialize = true;
}

function originForTheme(node) {
  const flag = node?.s1ThemeRestored;
  if (flag && flag.graphId === node.id) return "restored";
  if (flag || node?.s1ThemePendingRestore) return "duplicate";
  return "new";
}

function themeNodeLabel(node) {
  const raw = String(node?.title || "Theme");
  const title = raw.endsWith(THEME_CONFLICT_SUFFIX)
    ? raw.slice(0, -THEME_CONFLICT_SUFFIX.length)
    : raw;
  return `${title} #${node?.id}`;
}

function showThemeConflict(node, message) {
  const current = node.title || "Theme";
  const base = current.endsWith(THEME_CONFLICT_SUFFIX)
    ? current.slice(0, -THEME_CONFLICT_SUFFIX.length)
    : current;
  const next = message ? `${base}${THEME_CONFLICT_SUFFIX}` : base;
  node.s1ThemeIdConflict = message || "";
  if (current !== next) {
    node.title = next;
    node.setDirtyCanvas?.(true, true);
  }
}

function applyThemePlan(nodes) {
  for (const node of nodes) installThemeSerialize(node);
  const byKey = new Map();
  const entries = nodes.map((node, index) => {
    const key = `n${index}`;
    byKey.set(key, node);
    return {
      key,
      label: themeNodeLabel(node),
      origin: originForTheme(node),
      themeJson: widgetText(findWidget(node, "theme_json")),
    };
  });
  const plan = planThemeIds(entries);
  for (const assignment of plan.assignments) {
    const node = byKey.get(assignment.key);
    if (!node || typeof assignment.themeJson !== "string") continue;
    let nextJson = assignment.themeJson;
    const parsed = parseEditorDocument("theme", nextJson);
    if (parsed.ok) {
      const before = nextJson;
      assignThemeDocument(parsed.model);
      const committed = commitModel("theme", parsed.model);
      if (committed.ok) nextJson = committed.json;
      if (nextJson !== before) assignment.changed = true;
    }
    if (assignment.changed) writeNamed(node, "theme_json", nextJson);
  }
  const reasons = new Map();
  for (const conflict of plan.conflicts) {
    for (const key of conflict.keys) {
      const lines = reasons.get(key) || [];
      lines.push(conflict.reason);
      reasons.set(key, lines);
    }
  }
  for (const [key, node] of byKey) {
    const message = (reasons.get(key) || []).join(" ");
    showThemeConflict(node, message);
  }
  return plan;
}

// Rename option sockets to match theme_json. Unused pads with no live wire
// are hidden. Frontend 1.57.6 drops a wire when a connected socket is hidden
// or output.links is rewritten, so relinkOptionSlots never hides a live slot
// and never assigns output.links. Invalid JSON leaves sockets alone.
function syncOptionOutputs(node) {
  if (!isThemeNode(node)) return;
  orderThemePromptInputs(node);
  const plan = planOptionOutputs(widgetText(findWidget(node, "theme_json")));
  if (!plan.ok || !Array.isArray(plan.slots)) return;
  relinkOptionSlots(node, plan.slots);
  fitNode(node);
  node.graph?.setDirtyCanvas?.(true, true);
}

// Number theme ids on each loaded graph. Widget values are what queue serializes,
// so this runs before graphToPrompt reads them, not only when the modal opens.
// A nested subgraph is its own id space. Restored clashes are flagged and not
// rewritten. Option sockets are synced after the id write.
function reconcileThemeIds() {
  if (reconcilingThemes) return null;
  reconcilingThemes = true;
  try {
    const plans = themeGroups().map((nodes) => {
      const plan = applyThemePlan(nodes);
      for (const node of nodes) syncOptionOutputs(node);
      return plan;
    });
    if (state.node && editorVisible()) announceThemeConflict(state.node);
    return plans;
  } finally {
    reconcilingThemes = false;
  }
}

function scheduleThemeReconcile() {
  if (configuringGraph || themeReconcilePending) return;
  themeReconcilePending = true;
  const queue = typeof window !== "undefined" && window.setTimeout ? window.setTimeout.bind(window) : setTimeout;
  queue(() => {
    themeReconcilePending = false;
    if (configuringGraph) return;
    reconcileThemeIds();
  }, 0);
}

function installQueueHooks() {
  if (app.__s1ThemeQueueHooks) return;
  app.__s1ThemeQueueHooks = true;
  const wrap = (name) => {
    const original = app[name];
    if (typeof original !== "function") return;
    app[name] = function s1ThemeBeforeQueue(...args) {
      try {
        reconcileThemeIds();
      } catch (exc) {
        console.warn("[S1] theme id reconcile failed", exc);
      }
      return original.apply(this, args);
    };
  };
  // graphToPrompt reads widget values into the prompt. queuePrompt calls it
  // on the frontends that still expose both. There is no extension hook that
  // runs after a duplicate copies widgets and before that read.
  wrap("queuePrompt");
  wrap("graphToPrompt");
}

function isCollectNode(node) {
  const name = node?.comfyClass || node?.constructor?.comfyClass || node?.type || "";
  return name === "S1ThemeCollect";
}

function syncAllCollectInputs() {
  const graphs = themeGroups().map((nodes) => nodes[0]?.graph).filter(Boolean);
  const seen = new Set();
  const visit = (graph) => {
    if (!graph || seen.has(graph)) return;
    seen.add(graph);
    const nodes = graph._nodes || graph.nodes || [];
    for (const node of nodes) {
      if (isCollectNode(node)) {
        syncCollectInputs(node);
        node.graph?.setDirtyCanvas?.(true, true);
      }
      if (node?.subgraph) visit(node.subgraph);
    }
  };
  if (app.graph) visit(app.graph);
  for (const graph of graphs) visit(graph);
}

function installCollectNode(node) {
  if (!isCollectNode(node) || node.__s1CollectHooked) return;
  node.__s1CollectHooked = true;
  const original = node.onConnectionsChange;
  node.onConnectionsChange = function s1CollectConnectionsChange(...args) {
    const result = typeof original === "function" ? original.apply(this, args) : undefined;
    syncCollectInputs(this);
    this.graph?.setDirtyCanvas?.(true, true);
    return result;
  };
  syncCollectInputs(node);
}

app.registerExtension({
  name: "SystemOne.LoraRouter.UI",
  async setup() {
    installQueueHooks();
    ensureShell();
  },
  beforeConfigureGraph() {
    configuringGraph = true;
    restoredThisLoad.clear();
  },
  afterConfigureGraph() {
    configuringGraph = false;
    for (const node of restoredThisLoad) {
      if (!isThemeNode(node)) continue;
      node.s1ThemeRestored = { graphId: node.id };
      node.s1ThemePendingRestore = false;
    }
    restoredThisLoad.clear();
    reconcileThemeIds();
    syncAllCollectInputs();
  },
  loadedGraphNode(node) {
    if (!isThemeNode(node)) return;
    node.s1ThemeRestored = { graphId: node.id };
    node.s1ThemePendingRestore = false;
  },
  nodeCreated(node) {
    attachButton(node);
    installCollectNode(node);
    if (!isThemeNode(node)) return;
    orderThemePromptInputs(node);
    installThemeSerialize(node);
    if (configuringGraph) {
      // Saved widgets arrive in configure(), after this hook. Do not number yet.
      restoredThisLoad.add(node);
      node.s1ThemePendingRestore = true;
      return;
    }
    node.s1ThemePendingRestore = false;
    scheduleThemeReconcile();
  },
  getNodeMenuItems(node) {
    if (!specFor(node)) return;
    return [{ content: "Open visual editor", callback: () => { openEditorForNode(node); } }];
  },
});
