// Editor model for a LoRA library and one theme.
// Field rules match schema/types.py. This file does not import ComfyUI.
// Enable documents still parse here so old JSON can be recognized. The modal
// does not edit them. Option slots are planned here and applied by the editor.

export const SELECT_MODES = ["single", "multi"];
export const RUN_MODES = ["disabled", "enabled", "when_upstream"];
export const ENABLE_MATCH = ["any", "all"];
export const ENABLE_OPS = ["eq", "neq", "includes_any", "includes_all", "skipped", "answered"];

const BARE_OPS = new Set(["skipped", "answered"]);

export class EditorModelError extends Error {
  constructor(message) {
    super(message);
    this.name = "EditorModelError";
  }
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function fail(message) {
  throw new EditorModelError(message);
}

function rejectUnknown(data, allowed, path) {
  const extra = Object.keys(data)
    .filter((key) => !allowed.includes(key))
    .sort();
  if (extra.length) fail(`${path}: unknown field(s): ${extra.join(", ")}`);
}

function readVersion(data, path) {
  if (!Object.prototype.hasOwnProperty.call(data, "version")) return 1;
  const value = data.version;
  if (typeof value !== "number" || !Number.isInteger(value)) {
    fail(`${path}: version must be an integer`);
  }
  if (value !== 1) fail(`${path}: unsupported version ${value}; this package supports version 1 only`);
  return 1;
}

function requireText(value, path, allowEmpty = false) {
  if (typeof value !== "string") fail(`${path} must be a string`);
  if (!allowEmpty && value.trim() === "") fail(`${path} must be a non-empty string`);
  return value;
}

function requireId(value, path) {
  const text = requireText(value, path, false);
  if (/\s/.test(text)) fail(`${path} must not contain whitespace`);
  return text;
}

function requireName(value, path) {
  const text = requireText(value, path, false);
  if (text !== text.trim()) fail(`${path} must not have leading or trailing whitespace`);
  return text;
}

function requireChoice(value, allowed, path) {
  const text = requireText(value, path, false);
  if (!allowed.includes(text)) fail(`${path} must be one of: ${allowed.join(", ")}`);
  return text;
}

function finiteNumber(value, path) {
  if (typeof value === "boolean" || typeof value !== "number" || !Number.isFinite(value)) {
    fail(`${path} must be a finite number`);
  }
  return value;
}

function requireFloatField(data, key, path) {
  if (!Object.prototype.hasOwnProperty.call(data, key)) fail(`${path}: missing ${key}`);
  return finiteNumber(data[key], `${path}.${key}`);
}

function numberFromEditor(value, path, required) {
  if (value === undefined || value === null || value === "") {
    if (required) fail(`${path} must be a finite number`);
    return null;
  }
  if (typeof value === "number") return finiteNumber(value, path);
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed === "") {
      if (required) fail(`${path} must be a finite number`);
      return null;
    }
    if (!/^[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$/.test(trimmed)) {
      fail(`${path} must be a finite number`);
    }
    return finiteNumber(Number(trimmed), path);
  }
  fail(`${path} must be a finite number`);
}

function requireBool(value, path) {
  if (typeof value !== "boolean") fail(`${path} must be a boolean`);
  return value;
}

function stringList(value, path, { ids = false } = {}) {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    fail(`${path} must be a list of strings`);
  }
  if (ids) {
    for (const item of value) {
      if (item === "" || /\s/.test(item)) fail(`${path} entries must be ids without whitespace`);
    }
  }
  return value.slice();
}

function optionalId(data, key, path) {
  if (!Object.prototype.hasOwnProperty.call(data, key) || data[key] === null) return null;
  return requireId(data[key], `${path}.${key}`);
}

function rejectRemoved(data, path) {
  if (Object.prototype.hasOwnProperty.call(data, "lora_bindings")) {
    fail(`${path}: lora_bindings was removed; selected options contribute tags`);
  }
  if (Object.prototype.hasOwnProperty.call(data, "fallback_option_id")) {
    fail(`${path}: fallback_option_id was removed and is not applied`);
  }
}

function checkLoraEntry(data, path) {
  if (!isObject(data)) fail(`${path} must be an object`);
  rejectUnknown(data, ["lora_id", "name", "strength_model", "strength_clip", "tags", "enabled_default", "meta"], path);
  let meta = null;
  if (Object.prototype.hasOwnProperty.call(data, "meta")) {
    if (!isObject(data.meta)) fail(`${path}.meta must be an object`);
    meta = data.meta;
  }
  const tags = Object.prototype.hasOwnProperty.call(data, "tags") ? stringList(data.tags, `${path}.tags`) : [];
  const enabled = Object.prototype.hasOwnProperty.call(data, "enabled_default")
    ? requireBool(data.enabled_default, `${path}.enabled_default`)
    : true;
  return {
    lora_id: requireId(data.lora_id, `${path}.lora_id`),
    name: requireName(data.name, `${path}.name`),
    strength_model: requireFloatField(data, "strength_model", path),
    strength_clip: requireFloatField(data, "strength_clip", path),
    tags,
    enabled_default: enabled,
    meta: meta && Object.keys(meta).length ? structuredClone(meta) : null,
  };
}

function checkOption(data, path, seen) {
  if (!isObject(data)) fail(`${path} must be an object`);
  rejectRemoved(data, path);
  rejectUnknown(data, ["option_id", "label", "description", "tags"], path);
  const optionId = requireId(data.option_id, `${path}.option_id`);
  if (seen.has(optionId)) fail(`${path}: duplicate option_id ${optionId}`);
  seen.add(optionId);
  const tags = Object.prototype.hasOwnProperty.call(data, "tags") ? stringList(data.tags, `${path}.tags`) : [];
  return {
    option_id: optionId,
    label: requireText(data.label, `${path}.label`, true),
    description: requireText(data.description, `${path}.description`, true),
    tags,
  };
}

function checkTheme(data) {
  if (!isObject(data)) fail("theme must be an object");
  rejectRemoved(data, "theme");
  if (Object.prototype.hasOwnProperty.call(data, "themes")) {
    fail("theme: a theme node stores one theme; a library of themes is not accepted");
  }
  rejectUnknown(
    data,
    ["version", "theme_id", "title", "instructions", "select_mode", "options", "none_option_id"],
    "theme",
  );
  readVersion(data, "theme");
  if (!Array.isArray(data.options)) fail("theme: options must be a list");
  const seen = new Set();
  const options = data.options.map((item, index) => checkOption(item, `options[${index}]`, seen));
  const known = new Set(options.map((option) => option.option_id));
  const noneId = optionalId(data, "none_option_id", "theme");
  if (noneId !== null && !known.has(noneId)) {
    fail(`theme: none_option_id ${noneId} is not an option of this theme`);
  }
  return {
    version: 1,
    theme_id: requireId(data.theme_id, "theme.theme_id"),
    title: requireText(data.title, "theme.title"),
    instructions: requireText(data.instructions, "theme.instructions"),
    select_mode: requireChoice(data.select_mode, SELECT_MODES, "theme.select_mode"),
    options,
    none_option_id: noneId,
  };
}

function checkClause(data, path) {
  if (!isObject(data)) fail(`${path} must be an object`);
  rejectUnknown(data, ["theme_id", "op", "option_ids"], path);
  const op = requireChoice(data.op, ENABLE_OPS, `${path}.op`);
  let optionIds = [];
  if (BARE_OPS.has(op)) {
    if (
      Object.prototype.hasOwnProperty.call(data, "option_ids") &&
      data.option_ids != null &&
      !(Array.isArray(data.option_ids) && data.option_ids.length === 0)
    ) {
      fail(`${path}: op ${op} does not take option_ids`);
    }
  } else {
    if (!Object.prototype.hasOwnProperty.call(data, "option_ids")) fail(`${path}: missing option_ids`);
    optionIds = stringList(data.option_ids, `${path}.option_ids`, { ids: true });
    if ((op === "eq" || op === "neq") && optionIds.length !== 1) {
      fail(`${path}: op ${op} requires exactly one option_id`);
    }
    if ((op === "includes_any" || op === "includes_all") && optionIds.length < 1) {
      fail(`${path}: op ${op} requires at least one option_id`);
    }
  }
  return { theme_id: requireId(data.theme_id, `${path}.theme_id`), op, option_ids: optionIds };
}

function checkEnable(data) {
  if (!isObject(data)) fail("enable must be an object");
  rejectUnknown(data, ["version", "match", "clauses"], "enable");
  readVersion(data, "enable");
  const match = Object.prototype.hasOwnProperty.call(data, "match")
    ? requireChoice(data.match, ENABLE_MATCH, "enable.match")
    : "any";
  const raw = data.clauses === undefined ? [] : data.clauses;
  if (!Array.isArray(raw)) fail("enable: clauses must be a list");
  return {
    version: 1,
    match,
    clauses: raw.map((item, index) => checkClause(item, `clauses[${index}]`)),
  };
}

function checkLoraLibrary(data) {
  if (!isObject(data)) fail("lora library must be an object");
  rejectUnknown(data, ["version", "loras"], "lora library");
  readVersion(data, "lora library");
  if (!Array.isArray(data.loras)) fail("lora library: loras must be a list");
  const seen = new Set();
  const loras = data.loras.map((item, index) => {
    const entry = checkLoraEntry(item, `loras[${index}]`);
    if (seen.has(entry.lora_id)) fail(`loras[${index}]: duplicate lora_id ${entry.lora_id}`);
    seen.add(entry.lora_id);
    return entry;
  });
  return { version: 1, loras };
}

export function nextLoraId(existingIds) {
  const used = new Set();
  if (Array.isArray(existingIds)) {
    for (const item of existingIds) {
      if (typeof item === "string" && item !== "") used.add(item);
    }
  }
  let number = 1;
  while (used.has(`lora_${number}`)) number += 1;
  return `lora_${number}`;
}

function idKept(value) {
  return typeof value === "string" && value.trim() !== "";
}

export function assignLoraIds(model) {
  const loras = model?.loras;
  if (!Array.isArray(loras)) return model;
  const seen = [];
  for (const entry of loras) {
    if (entry && idKept(entry.lora_id)) seen.push(entry.lora_id);
  }
  for (const entry of loras) {
    if (!entry || typeof entry !== "object") continue;
    if (idKept(entry.lora_id)) continue;
    const id = nextLoraId(seen);
    entry.lora_id = id;
    seen.push(id);
  }
  return model;
}

function nextPrefixedId(prefix, existingIds) {
  const used = new Set();
  if (Array.isArray(existingIds)) {
    for (const item of existingIds) {
      if (typeof item === "string" && item !== "") used.add(item);
    }
  }
  let number = 1;
  while (used.has(`${prefix}${number}`)) number += 1;
  return `${prefix}${number}`;
}

export function nextThemeId(existingIds) {
  return nextPrefixedId("theme_", existingIds);
}

export function nextOptionId(existingIds) {
  return nextPrefixedId("option_", existingIds);
}

export function assignOptionIds(options) {
  if (!Array.isArray(options)) return options;
  const seen = [];
  for (const option of options) {
    if (option && idKept(option.option_id)) seen.push(option.option_id);
  }
  for (const option of options) {
    if (!option || typeof option !== "object") continue;
    if (idKept(option.option_id)) continue;
    const id = nextOptionId(seen);
    option.option_id = id;
    seen.push(id);
  }
  return options;
}

export const DEFAULT_NONE_LABEL = "None";
export const DEFAULT_NONE_DESCRIPTION = "None";
export const PREFERRED_NONE_OPTION_ID = "none";
// Former auto-generated default. Kept only to recognize and relabel saved None rows.
export const LEGACY_DEFAULT_NONE_TEXT = "以上皆非";
const NONE_LIKE_IDS = new Set(["none", "__none__", LEGACY_DEFAULT_NONE_TEXT]);
const NONE_LIKE_LABELS = new Set([LEGACY_DEFAULT_NONE_TEXT, "none", "none of the above", "not on the list"]);

function normText(value) {
  return String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
}

export function isNoneLikeOption(option) {
  if (!option || typeof option !== "object") return false;
  const optionId = normText(option.option_id);
  if (optionId && NONE_LIKE_IDS.has(optionId)) return true;
  const label = normText(option.label);
  if (label && NONE_LIKE_LABELS.has(label)) return true;
  const description = normText(option.description);
  if (description && NONE_LIKE_LABELS.has(description)) return true;
  return false;
}

/** True only when a field is exactly the former auto-generated default (trimmed). */
export function isLegacyDefaultNoneText(value) {
  return String(value ?? "").trim() === LEGACY_DEFAULT_NONE_TEXT;
}

/**
 * Relabel the designated None option when a field is clearly the former
 * auto-generated default "以上皆非". Never rewrites user-typed text, tags,
 * option_id, or any other option.
 */
export function relabelLegacyDefaultNoneOption(option) {
  if (!option || typeof option !== "object") return false;
  let changed = false;
  if (isLegacyDefaultNoneText(option.label)) {
    option.label = DEFAULT_NONE_LABEL;
    changed = true;
  }
  if (isLegacyDefaultNoneText(option.description)) {
    option.description = DEFAULT_NONE_DESCRIPTION;
    changed = true;
  }
  return changed;
}

function applyLegacyNoneRelabel(model) {
  const noneId = String(model?.none_option_id || "").trim();
  if (!noneId || !Array.isArray(model.options)) return false;
  const option = model.options.find((item) => String(item?.option_id || "") === noneId);
  return relabelLegacyDefaultNoneOption(option);
}

function nextNoneOptionId(existingIds) {
  const used = new Set();
  if (existingIds && typeof existingIds[Symbol.iterator] === "function") {
    for (const item of existingIds) used.add(String(item));
  }
  if (!used.has(PREFERRED_NONE_OPTION_ID)) return PREFERRED_NONE_OPTION_ID;
  let index = 2;
  while (used.has(`${PREFERRED_NONE_OPTION_ID}_${index}`)) index += 1;
  return `${PREFERRED_NONE_OPTION_ID}_${index}`;
}

export function ensureDefaultNoneOption(model) {
  if (!model || typeof model !== "object" || Array.isArray(model)) {
    return { model, changed: false, reused: false, added: false };
  }
  const options = Array.isArray(model.options) ? model.options : [];
  model.options = options;
  const known = new Set(options.map((option) => String(option?.option_id || "")).filter(Boolean));
  const current = String(model.none_option_id || "").trim();
  if (current && known.has(current)) {
    model.none_option_id = current;
    const relabeled = applyLegacyNoneRelabel(model);
    return { model, changed: relabeled, reused: true, added: false };
  }
  for (const option of options) {
    if (!isNoneLikeOption(option)) continue;
    if (!idKept(option.option_id)) {
      option.option_id = nextNoneOptionId(known);
      known.add(option.option_id);
    }
    model.none_option_id = option.option_id;
    const relabeled = applyLegacyNoneRelabel(model);
    return { model, changed: true, reused: true, added: false, relabeled };
  }
  if (options.length >= MAX_OPTION_OUTPUTS) {
    return { model, changed: false, reused: false, added: false, error: `cannot add ${DEFAULT_NONE_LABEL}; option outputs are capped at ${MAX_OPTION_OUTPUTS}` };
  }
  const optionId = nextNoneOptionId(known);
  options.push({
    option_id: optionId,
    label: DEFAULT_NONE_LABEL,
    description: DEFAULT_NONE_DESCRIPTION,
    tags: [],
  });
  model.none_option_id = optionId;
  return { model, changed: true, reused: false, added: true };
}

export function assignThemeDocument(model) {
  if (!model || typeof model !== "object" || Array.isArray(model)) return model;
  if (!idKept(model.theme_id)) model.theme_id = nextThemeId([]);
  assignOptionIds(model.options);
  ensureDefaultNoneOption(model);
  assignOptionIds(model.options);
  return model;
}

// theme_1, theme_2, ... with no leading zeros. theme_01 and art_style are manual.
export function isAutoThemeId(value) {
  return typeof value === "string" && /^theme_[1-9]\d*$/.test(value);
}

function themePayload(themeJson) {
  if (typeof themeJson === "string") {
    try {
      const data = JSON.parse(themeJson.replace(/^\uFEFF/, ""));
      if (!isObject(data)) return { ok: false, error: "theme_json must be a JSON object" };
      return { ok: true, data };
    } catch (exc) {
      return { ok: false, error: `Invalid JSON: ${exc.message}` };
    }
  }
  if (isObject(themeJson)) return { ok: true, data: themeJson };
  return { ok: false, error: "theme_json must be a JSON object" };
}

function storedThemeId(data) {
  const value = data?.theme_id;
  if (!idKept(value)) return "";
  return value;
}

function withThemeId(data, themeId) {
  const out = {};
  let sawId = false;
  for (const key of Object.keys(data)) {
    if (key === "theme_id") {
      out.theme_id = themeId;
      sawId = true;
    } else out[key] = data[key];
  }
  if (sawId) return out;
  const ordered = {};
  if (Object.prototype.hasOwnProperty.call(out, "version")) {
    ordered.version = out.version;
    delete out.version;
  }
  ordered.theme_id = themeId;
  for (const key of Object.keys(out)) ordered[key] = out[key];
  return ordered;
}

function entryLabel(row) {
  return row.label || row.key;
}

/**
 * Assign graph-unique theme ids without rewriting enable rules.
 *
 * `entries` are in graph order. Each is `{key, label, origin, themeJson, enableJson}`.
 * `origin` is `new`, `duplicate`, or `restored`.
 *
 * A new or duplicated node keeps a non-empty id that nobody else kept, and
 * otherwise takes the lowest free theme_N. Restored non-empty ids are claimed
 * first, so a new theme_1 does not displace a saved theme_1. Two restored
 * nodes that share a non-empty id are a conflict: both documents stay, because
 * renaming one would retarget a saved enable rule that names that id.
 * A blank restored id is filled. enableJson is never edited.
 */
export function planThemeIds(entries) {
  const list = Array.isArray(entries) ? entries : [];
  const rows = list.map((entry, index) => {
    const key = entry && entry.key != null && String(entry.key) !== "" ? String(entry.key) : `entry_${index}`;
    const origin = entry?.origin === "restored" || entry?.origin === "duplicate" ? entry.origin : "new";
    const parsed = themePayload(entry?.themeJson);
    return {
      index,
      key,
      label: entry?.label ? String(entry.label) : "",
      origin,
      themeJson: entry?.themeJson,
      enableJson: entry?.enableJson,
      parsed,
      themeId: parsed.ok ? storedThemeId(parsed.data) : "",
    };
  });

  const conflicts = [];
  const restoredById = new Map();
  for (const row of rows) {
    if (!row.parsed.ok) {
      conflicts.push({
        themeId: "",
        keys: [row.key],
        reason: `Node ${entryLabel(row)} has unreadable theme_json (${row.parsed.error}). It was left unchanged.`,
      });
      continue;
    }
    if (row.origin !== "restored" || !row.themeId) continue;
    const keys = restoredById.get(row.themeId) || [];
    keys.push(row.key);
    restoredById.set(row.themeId, keys);
  }
  const contested = new Set();
  for (const [themeId, keys] of restoredById) {
    if (keys.length < 2) continue;
    contested.add(themeId);
    const labels = keys.map((key) => entryLabel(rows.find((row) => row.key === key)));
    conflicts.push({
      themeId,
      keys: keys.slice(),
      reason:
        `Restored nodes share theme_id ${JSON.stringify(themeId)} (${labels.join(", ")}). ` +
        "Their theme JSON was left unchanged. A decision chain still rejects a repeated theme_id.",
    });
  }

  const used = new Set(contested);
  const decisionByKey = new Map();
  for (const row of rows) {
    if (!row.parsed.ok) {
      decisionByKey.set(row.key, { changed: false, themeId: "" });
      continue;
    }
    if (row.origin === "restored" && row.themeId) {
      if (!contested.has(row.themeId)) used.add(row.themeId);
      decisionByKey.set(row.key, { changed: false, themeId: row.themeId });
    }
  }
  for (const row of rows) {
    if (decisionByKey.has(row.key)) continue;
    let themeId = row.themeId;
    let changed = false;
    if (!themeId || used.has(themeId)) {
      themeId = nextThemeId([...used]);
      changed = true;
    }
    used.add(themeId);
    decisionByKey.set(row.key, { changed, themeId });
  }

  const assignments = [];
  const unchanged = [];
  for (const row of rows) {
    const decision = decisionByKey.get(row.key);
    let themeJson = row.themeJson;
    if (decision.changed) {
      const next = withThemeId(row.parsed.data, decision.themeId);
      themeJson = typeof row.themeJson === "string" ? JSON.stringify(next, null, 2) : next;
    }
    assignments.push({
      key: row.key,
      themeId: decision.themeId,
      themeJson,
      changed: decision.changed,
      enableJson: row.enableJson,
      conflict: conflicts.some((conflict) => conflict.keys.includes(row.key)),
    });
    if (!decision.changed) unchanged.push(row.key);
  }
  return { assignments, conflicts, unchanged };
}

export const MAX_OPTION_OUTPUTS = 32;
export const DECISION_TYPE = "S1_DECISION";
export const REPORT_OUTPUT_INDEX = MAX_OPTION_OUTPUTS;

/** Internal slot name. A label and an id become "label (id)". Not shown in the UI. */
export function optionOutputName(option) {
  const id = option && option.option_id != null ? String(option.option_id) : "";
  const label = option && option.label != null ? String(option.label).trim() : "";
  if (label && id) return `${label} (${id})`;
  return id || label;
}

/** Visible option text from label, then description. Does not include option_id. */
export function optionDisplayText(option) {
  const label = option && option.label != null ? String(option.label).trim() : "";
  const description = option && option.description != null ? String(option.description).trim() : "";
  return label || description;
}

/**
 * Visible socket labels in options-array / prompt-index order.
 * Display numbers follow the table (user options, then None last).
 * Empty text becomes "Option N". Duplicate names keep the first bare and
 * suffix later ones with " #N" using the table display number.
 * Never includes option_id.
 */
export function optionOutputLabels(options, noneOptionId) {
  const list = Array.isArray(options) ? options : [];
  const displayed = optionDisplayOrder(list, noneOptionId);
  const rows = displayed.map((option, index) => {
    const number = index + 1;
    const raw = optionDisplayText(option);
    return { option, number, raw: raw || `Option ${number}` };
  });
  const counts = new Map();
  for (const row of rows) counts.set(row.raw, (counts.get(row.raw) || 0) + 1);
  const seen = new Map();
  const byOption = new Map();
  for (const row of rows) {
    let text = row.raw;
    if ((counts.get(row.raw) || 0) > 1) {
      const next = (seen.get(row.raw) || 0) + 1;
      seen.set(row.raw, next);
      if (next > 1) text = `${row.raw} #${row.number}`;
    }
    byOption.set(row.option, text);
  }
  return list.map((option, index) => byOption.get(option) || optionDisplayText(option) || `Option ${index + 1}`);
}

/**
 * Plan the 32 option sockets for one theme document.
 * Invalid JSON returns ok:false and slots:null. The caller leaves outputs alone.
 */
export function planOptionOutputs(themeJson) {
  const text = typeof themeJson === "string" ? themeJson : JSON.stringify(themeJson ?? null);
  const parsed = parseEditorDocument("theme", text);
  if (!parsed.ok) return { ok: false, error: parsed.error, slots: null };
  ensureDefaultNoneOption(parsed.model);
  const options = parsed.model.options || [];
  if (options.length > MAX_OPTION_OUTPUTS) {
    return {
      ok: false,
      error: `This theme has ${options.length} options. Option outputs are capped at ${MAX_OPTION_OUTPUTS}.`,
      slots: null,
    };
  }
  const displayLabels = optionOutputLabels(options, parsed.model.none_option_id);
  const slots = [];
  for (let index = 0; index < MAX_OPTION_OUTPUTS; index += 1) {
    if (index < options.length) {
      const option = options[index];
      const visible = displayLabels[index] || optionDisplayText(option) || `Option ${index + 1}`;
      slots.push({
        index,
        option_id: String(option.option_id || ""),
        name: optionOutputName(option),
        label: visible,
        localized_name: visible,
        type: DECISION_TYPE,
        hidden: false,
      });
    } else {
      // `hidden` marks an unused pad in the plan. relinkOptionSlots does not
      // copy it onto `output.hidden`: ComfyUI frontend 1.57.6 keeps link truth
      // in `graph.links`, and hiding a socket drops wires.
      slots.push({ index, option_id: "", name: "", type: DECISION_TYPE, hidden: true });
    }
  }
  return { ok: true, slots, reportIndex: REPORT_OUTPUT_INDEX };
}

/** Visible label for an option pad that theme_json does not use. */
export const UNUSED_OPTION_LABEL = "·";

function sameNodeId(left, right) {
  if (left == null || right == null) return false;
  return String(left) === String(right);
}

function asSlot(value) {
  if (typeof value === "number" && Number.isInteger(value)) return value;
  if (typeof value === "string" && /^-?\d+$/.test(value)) return Number(value);
  return null;
}

function linkParts(link) {
  if (Array.isArray(link)) {
    return {
      id: link[0],
      originId: link[1],
      originSlot: link[2],
      targetId: link[3],
      targetSlot: link[4],
    };
  }
  if (link && typeof link === "object") {
    // Legacy LiteGraph objects use origin_id. Frontend 1.57 LLink state and
    // some in-memory copies use originId. Either one is the wire.
    return {
      id: link.id,
      originId: link.origin_id != null ? link.origin_id : link.originId,
      originSlot: link.origin_slot != null ? link.origin_slot : link.originSlot,
      targetId: link.target_id != null ? link.target_id : link.targetId,
      targetSlot: link.target_slot != null ? link.target_slot : link.targetSlot,
    };
  }
  return null;
}

function writeOriginSlot(link, slot) {
  if (Array.isArray(link)) {
    link[2] = slot;
    return;
  }
  if (!link || typeof link !== "object") return;
  const hasSnake = "origin_slot" in link;
  const hasCamel = "originSlot" in link;
  if (hasSnake || !hasCamel) link.origin_slot = slot;
  if (hasCamel) link.originSlot = slot;
}

function eachGraphLink(graph, visit) {
  const links = graph?.links;
  if (!links) return;
  if (Array.isArray(links)) {
    for (let index = 0; index < links.length; index += 1) {
      if (links[index]) visit(links[index]);
    }
    return;
  }
  // Frontend 1.57 stores links in a Map (proxied so links[id] still works).
  // Object.keys on a raw Map is empty, so the Map is the source of truth.
  if (typeof links.entries === "function" && typeof links.get === "function") {
    for (const [, link] of links.entries()) {
      if (link) visit(link);
    }
    return;
  }
  for (const key of Object.keys(links)) {
    if (links[key]) visit(links[key]);
  }
}

function outputHasLinks(output) {
  if (!output) return false;
  const links = output.links;
  if (Array.isArray(links) && links.length) return true;
  if (links != null && links !== false && !Array.isArray(links)) return true;
  return false;
}

function linksAssignmentDropsWires(output) {
  // NodeOutputSlot.links in frontend 1.57 is a setter. Assigning an array
  // that omits an id disconnects that link in the link store.
  let cursor = output;
  while (cursor && cursor !== Object.prototype) {
    const desc = Object.getOwnPropertyDescriptor(cursor, "links");
    if (desc) return typeof desc.set === "function";
    cursor = Object.getPrototypeOf(cursor);
  }
  return false;
}

function forgetPlainLink(output, id) {
  if (!output || linksAssignmentDropsWires(output) || !Array.isArray(output.links)) return;
  const index = output.links.indexOf(id);
  if (index >= 0) output.links.splice(index, 1);
}

function rememberPlainLink(output, id) {
  if (!output || linksAssignmentDropsWires(output)) return;
  if (Array.isArray(output.links)) {
    if (!output.links.includes(id)) output.links.push(id);
    return;
  }
  if (output.links == null) output.links = [id];
}

function liveOriginSlots(node) {
  const live = new Set();
  eachGraphLink(node?.graph, (link) => {
    const parts = linkParts(link);
    if (!parts || !sameNodeId(parts.originId, node.id)) return;
    const index = asSlot(parts.originSlot);
    if (index == null || index < 0 || index >= REPORT_OUTPUT_INDEX) return;
    live.add(index);
  });
  return live;
}

function ensureOutput(outputs, index, type) {
  while (outputs.length <= index) outputs.push(null);
  if (!outputs[index] || typeof outputs[index] !== "object") {
    outputs[index] = { name: "", type, links: null };
  }
  return outputs[index];
}

/**
 * Rename option sockets and retarget wires by option id.
 *
 * The first sync (no output has s1OptionId) stamps ids by index and does not
 * move or delete links. A later sync moves graph.links origin_slot /
 * originSlot to the option's new index. A link with no previous s1OptionId
 * stays on its slot so the stamp can claim it. A link whose option id is
 * gone from theme_json stays connected too: deleting it, or rewriting
 * output.links, is what dropped Theme Collect wires on frontend 1.57.6.
 * Links on the report socket (index 32) stay put. A report_json name alone
 * does not count as a prior sync.
 *
 * Live means output.links or a graph.links entry whose origin is this node
 * and this slot (origin_id/originId, origin_slot/originSlot). Frontend 1.57
 * often has the wire only in graph.links. Unused pads that have no live
 * wire may set output.hidden so only defined options show. A connected
 * slot is never hidden. Assigning output.links is still forbidden: that
 * setter disconnects the wire on frontend 1.57.6.
 */
export function relinkOptionSlots(node, slots) {
  if (!node || !Array.isArray(slots) || slots.length < MAX_OPTION_OUTPUTS) {
    return { ok: false, first: true, moved: 0, dropped: 0, kept: 0 };
  }
  if (!Array.isArray(node.outputs)) node.outputs = [];
  const outputs = node.outputs;
  const first = !outputs.some(
    (output, index) => index < MAX_OPTION_OUTPUTS && output && output.s1OptionId,
  );
  const previous = [];
  for (let index = 0; index < MAX_OPTION_OUTPUTS; index += 1) {
    const stamped = outputs[index]?.s1OptionId;
    previous.push(stamped ? String(stamped) : "");
  }
  let moved = 0;
  let dropped = 0;
  let kept = 0;
  if (!first && node.graph) {
    const nextIndex = new Map();
    slots.forEach((slot, index) => {
      if (index < MAX_OPTION_OUTPUTS && slot?.option_id) nextIndex.set(String(slot.option_id), index);
    });
    const jobs = [];
    eachGraphLink(node.graph, (link) => {
      const parts = linkParts(link);
      if (!parts || !sameNodeId(parts.originId, node.id)) return;
      const from = asSlot(parts.originSlot);
      if (from == null || from < 0 || from >= REPORT_OUTPUT_INDEX) return;
      const optionId = previous[from] || "";
      // Empty id: this wire was never stamped. Leave it here. The loop below
      // writes s1OptionId for the slot without removing the graph link.
      if (!optionId) return;
      if (!nextIndex.has(optionId)) {
        // Option is gone and the wire is still in graph.links. Keep it.
        kept += 1;
        return;
      }
      const to = nextIndex.get(optionId);
      if (to === from) return;
      jobs.push({ link, id: parts.id, from, to });
    });
    for (const job of jobs) {
      // Do not assign output.links. On frontend 1.57 that setter disconnects
      // any id missing from the new array, including the wire being moved.
      forgetPlainLink(outputs[job.from], job.id);
      writeOriginSlot(job.link, job.to);
      rememberPlainLink(ensureOutput(outputs, job.to, DECISION_TYPE), job.id);
      moved += 1;
    }
  }
  const liveSlots = liveOriginSlots(node);
  for (let index = 0; index < MAX_OPTION_OUTPUTS; index += 1) {
    const slot = slots[index];
    const output = ensureOutput(outputs, index, DECISION_TYPE);
    const live = outputHasLinks(output) || liveSlots.has(index);
    const plannedUnused = Boolean(slot.hidden);
    if (!plannedUnused && slot.name) output.name = slot.name;
    else if (plannedUnused && !live) output.name = UNUSED_OPTION_LABEL;
    else if (!output.name) output.name = UNUSED_OPTION_LABEL;
    // Vue Nodes 2.0 and classic canvas both show
    // label || localized_name || name. Keep output.name as the internal
    // slot name; only the visible fields drop option_id.
    if (!plannedUnused && (slot.label || slot.localized_name)) {
      const visible = slot.label || slot.localized_name;
      output.label = visible;
      output.localized_name = visible;
    } else if (plannedUnused && !live) {
      output.label = UNUSED_OPTION_LABEL;
      output.localized_name = UNUSED_OPTION_LABEL;
    } else {
      output.label = output.label || output.name;
      output.localized_name = output.localized_name || output.label || output.name;
    }
    output.type = DECISION_TYPE;
    // Hide only unused pads with no live wire. Frontend 1.57.6 drops a
    // link when a connected socket is hidden, and assigning output.links
    // disconnects it. Connected slots stay visible and untouched.
    output.hidden = Boolean(plannedUnused && !live);
    output.s1OptionId = slot.option_id || "";
  }
  const report = ensureOutput(outputs, REPORT_OUTPUT_INDEX, "STRING");
  if (!report.name) report.name = "report_json";
  if (!report.type || report.type === DECISION_TYPE) report.type = "STRING";
  report.hidden = false;
  report.s1PromptIndex = REPORT_OUTPUT_INDEX;
  return { ok: true, first, moved, dropped, kept };
}

export const PROMPT_INDEX_FIELD = "s1PromptIndex";

function remapOriginSlots(node, indexMap) {
  if (!node?.graph || !indexMap || !indexMap.size) return;
  eachGraphLink(node.graph, (link) => {
    const parts = linkParts(link);
    if (!parts || !sameNodeId(parts.originId, node.id)) return;
    const from = asSlot(parts.originSlot);
    if (from == null || !indexMap.has(from)) return;
    const to = indexMap.get(from);
    if (to === from) return;
    writeOriginSlot(link, to);
  });
}

/**
 * Restore the full 32 option pads + report_json at index 32.
 *
 * Frontend 1.57.6 Vue Nodes 2.0 (Comfy.VueNodes.Enabled) renders
 * `nodeData.outputs` with no `slot.hidden` filter, so display uses a
 * compacted array. Execution and saved workflows still use fixed indexes
 * (report_json is always 32). Expand before graphToPrompt / serialize.
 * Never assigns output.links.
 */
export function expandOptionOutputs(node) {
  if (!node) return { ok: false, expanded: false };
  if (!Array.isArray(node.outputs)) node.outputs = [];
  const current = node.outputs.filter(Boolean);
  const fullLen = REPORT_OUTPUT_INDEX + 1;
  const alreadyFull = node.outputs.length >= fullLen && node.outputs[REPORT_OUTPUT_INDEX];
  if (alreadyFull) {
    for (let index = 0; index < fullLen; index += 1) {
      const output = ensureOutput(node.outputs, index, index === REPORT_OUTPUT_INDEX ? "STRING" : DECISION_TYPE);
      output.s1PromptIndex = index;
    }
    return { ok: true, expanded: false };
  }
  const placed = new Array(fullLen).fill(null);
  const indexMap = new Map();
  current.forEach((output, visual) => {
    let prompt = Number.isInteger(output.s1PromptIndex) ? output.s1PromptIndex : -1;
    if (prompt < 0) {
      const isReport = output.name === "report_json" || (output.type === "STRING" && output.type !== DECISION_TYPE);
      prompt = isReport ? REPORT_OUTPUT_INDEX : visual;
    }
    if (prompt < 0 || prompt >= fullLen) return;
    if (!placed[prompt]) placed[prompt] = output;
    indexMap.set(visual, prompt);
  });
  for (let index = 0; index < fullLen; index += 1) {
    if (placed[index]) {
      placed[index].s1PromptIndex = index;
      continue;
    }
    if (index === REPORT_OUTPUT_INDEX) {
      placed[index] = { name: "report_json", type: "STRING", hidden: false, s1PromptIndex: index };
    } else {
      placed[index] = { name: UNUSED_OPTION_LABEL, type: DECISION_TYPE, hidden: true, s1OptionId: "", s1PromptIndex: index };
    }
  }
  node.outputs = placed;
  remapOriginSlots(node, indexMap);
  return { ok: true, expanded: true };
}

/**
 * Drop unused unconnected option pads so Vue Nodes 2.0 does not paint them.
 * Connected / live sockets are never removed. report_json stays in the
 * visible list but keeps s1PromptIndex 32 for prompt expansion.
 * Only trailing (and interstitial unused) unconnected pads go away; option
 * backend indexes of kept slots do not change.
 */
function noneOptionIdFromWidget(node) {
  const widgets = node?.widgets || [];
  for (const widget of widgets) {
    if (widget?.name !== "theme_json") continue;
    const raw = widget.value == null ? "" : String(widget.value);
    const parsed = parseEditorDocument("theme", raw);
    if (!parsed.ok) return "";
    ensureDefaultNoneOption(parsed.model);
    return String(parsed.model.none_option_id || "");
  }
  return "";
}

function isNoneOutput(output, noneId) {
  if (!output) return false;
  const optionId = String(output.s1OptionId || "");
  if (noneId && optionId && optionId === String(noneId)) return true;
  if (optionId && isNoneLikeOption({ option_id: optionId })) return true;
  return false;
}

export function compactOptionOutputs(node, noneOptionId) {
  if (!node) return { ok: false };
  expandOptionOutputs(node);
  const noneId = noneOptionId || noneOptionIdFromWidget(node);
  const liveSlots = liveOriginSlots(node);
  const regular = [];
  const noneOuts = [];
  for (let index = 0; index < MAX_OPTION_OUTPUTS; index += 1) {
    const output = node.outputs[index];
    const live = outputHasLinks(output) || liveSlots.has(index);
    const used = Boolean(output?.s1OptionId);
    if (!used && !live) continue;
    output.hidden = false;
    output.s1PromptIndex = index;
    if (isNoneOutput(output, noneId)) noneOuts.push([index, output]);
    else regular.push([index, output]);
  }
  const kept = [];
  const indexMap = new Map();
  for (const [index, output] of regular.concat(noneOuts)) {
    indexMap.set(index, kept.length);
    kept.push(output);
  }
  const report = ensureOutput(node.outputs, REPORT_OUTPUT_INDEX, "STRING");
  if (!report.name) report.name = "report_json";
  report.type = "STRING";
  report.hidden = false;
  report.s1PromptIndex = REPORT_OUTPUT_INDEX;
  indexMap.set(REPORT_OUTPUT_INDEX, kept.length);
  kept.push(report);
  node.outputs = kept;
  remapOriginSlots(node, indexMap);
  return { ok: true, visible: kept.length, noneLast: noneOuts.length ? kept.length - 2 : -1 };
}

/**
 * Keep the negative socket immediately under positive.
 *
 * ComfyUI lists every required input before optional ones, so an optional
 * negative would otherwise sit under settings. Moving the input object keeps
 * prompt order without making negative required. Existing links are remapped
 * to the new target_slot.
 */
export function orderThemePromptInputs(node) {
  if (!node || !Array.isArray(node.inputs)) {
    return { ok: false, moved: false };
  }
  const inputs = node.inputs;
  const pos = inputs.findIndex((item) => item && item.name === "positive");
  const neg = inputs.findIndex((item) => item && item.name === "negative");
  if (pos < 0 || neg < 0 || neg === pos + 1) {
    return { ok: pos >= 0 && (neg < 0 || neg === pos + 1), moved: false };
  }
  const [negative] = inputs.splice(neg, 1);
  const insertAt = inputs.findIndex((item) => item && item.name === "positive") + 1;
  inputs.splice(insertAt, 0, negative);
  if (node.graph) {
    inputs.forEach((input, index) => {
      const linkId = input?.link;
      if (linkId == null) return;
      const links = node.graph.links;
      const link = Array.isArray(links) ? links[linkId] : links?.[linkId];
      if (!link) return;
      if (Array.isArray(link)) link[4] = index;
      else link.target_slot = index;
    });
  }
  return { ok: true, moved: true };
}

export function fieldPathsFromError(message) {
  const text = String(message || "");
  const paths = [];
  const seen = new Set();
  const add = (path) => {
    const normalized = String(path).replace(/\[(\d+)\]/g, ".$1");
    if (!normalized || seen.has(normalized)) return;
    seen.add(normalized);
    paths.push(normalized);
  };
  const pattern = /\b((?:loras|options|clauses)(?:\[\d+\]|\.[A-Za-z_][\w]*)+)/g;
  let match = pattern.exec(text);
  while (match) {
    add(match[1]);
    match = pattern.exec(text);
  }
  const extras = [];
  if (/duplicate option_id/.test(text)) extras.push("option_id");
  if (/duplicate lora_id/.test(text)) extras.push("lora_id");
  if (/\bnone_option_id\b/.test(text)) extras.push("none_option_id");
  if (/\boption_ids\b/.test(text) || /exactly one option_id/.test(text)) extras.push("option_ids");
  if (extras.length && paths.length) {
    const base = paths[0];
    for (const name of extras) {
      if (base.endsWith(`.${name}`) || base.split(".").includes(name)) continue;
      add(`${base}.${name}`);
    }
  } else {
    for (const name of extras) add(name);
  }
  return paths;
}

function sharedStrength(entry, path) {
  const hasEditorField = entry && Object.prototype.hasOwnProperty.call(entry, "strength");
  const source = hasEditorField ? entry.strength : entry?.strength_model;
  return numberFromEditor(source, `${path}.strength`, true);
}

function tagsFromEditor(value) {
  if (Array.isArray(value)) return value.map((item) => String(item));
  if (typeof value === "string") {
    return value
      .split(",")
      .map((item) => item.trim())
      .filter((item) => item !== "");
  }
  return [];
}

function documentFromLora(model) {
  if (model && Array.isArray(model.loras)) assignLoraIds(model);
  const loras = (model?.loras || []).map((entry, index) => {
    const path = `loras[${index}]`;
    const strength = sharedStrength(entry, path);
    const out = {
      lora_id: entry.lora_id ?? "",
      name: entry.name ?? "",
      strength_model: strength,
      strength_clip: strength,
    };
    const tags = tagsFromEditor(entry.tags);
    if (tags.length) out.tags = tags;
    if (entry.enabled_default === false) out.enabled_default = false;
    if (entry.meta && isObject(entry.meta) && Object.keys(entry.meta).length) out.meta = entry.meta;
    return out;
  });
  return checkLoraLibrary({ version: 1, loras });
}

function documentFromTheme(model) {
  if (model && typeof model === "object") assignThemeDocument(model);
  const options = (model?.options || []).map((option) => ({
    option_id: option?.option_id ?? "",
    label: option?.label ?? "",
    description: option?.description ?? "",
    tags: tagsFromEditor(option?.tags),
  }));
  const doc = {
    version: 1,
    theme_id: model?.theme_id ?? "",
    title: model?.title ?? "",
    instructions: model?.instructions ?? "",
    select_mode: model?.select_mode ?? "",
    options: options.map((option) => {
      const out = {
        option_id: option.option_id,
        label: option.label,
        description: option.description,
      };
      if (option.tags.length) out.tags = option.tags;
      return out;
    }),
  };
  const none = model?.none_option_id;
  if (none !== undefined && none !== null && none !== "") doc.none_option_id = none;
  return checkTheme(doc);
}

function documentFromEnable(model) {
  const clauses = (model?.clauses || []).map((clause) => {
    const op = clause?.op ?? "";
    const out = { theme_id: clause?.theme_id ?? "", op };
    if (!BARE_OPS.has(op)) out.option_ids = tagsFromEditor(clause?.option_ids);
    return out;
  });
  return checkEnable({ version: 1, match: model?.match || "any", clauses });
}

function emitLora(checked) {
  return {
    version: 1,
    loras: checked.loras.map((entry) => {
      const out = {
        lora_id: entry.lora_id,
        name: entry.name,
        strength_model: entry.strength_model,
        strength_clip: entry.strength_clip,
      };
      if (entry.tags.length) out.tags = entry.tags.slice();
      if (!entry.enabled_default) out.enabled_default = false;
      if (entry.meta) out.meta = entry.meta;
      return out;
    }),
  };
}

function emitTheme(checked) {
  const out = {
    version: 1,
    theme_id: checked.theme_id,
    title: checked.title,
    instructions: checked.instructions,
    select_mode: checked.select_mode,
    options: checked.options.map((option) => {
      const item = {
        option_id: option.option_id,
        label: option.label,
        description: option.description,
      };
      if (option.tags.length) item.tags = option.tags.slice();
      return item;
    }),
  };
  if (checked.none_option_id) out.none_option_id = checked.none_option_id;
  return out;
}

function emitEnable(checked) {
  return {
    version: 1,
    match: checked.match,
    clauses: checked.clauses.map((clause) => {
      const out = { theme_id: clause.theme_id, op: clause.op };
      if (!BARE_OPS.has(clause.op)) out.option_ids = clause.option_ids.slice();
      return out;
    }),
  };
}

function editorFromChecked(kind, checked) {
  if (kind === "lora") return { version: 1, loras: checked.loras };
  if (kind === "theme") {
    return {
      version: 1,
      theme_id: checked.theme_id,
      title: checked.title,
      instructions: checked.instructions,
      select_mode: checked.select_mode,
      options: checked.options,
      none_option_id: checked.none_option_id || "",
    };
  }
  if (kind === "enable") return { version: 1, match: checked.match, clauses: checked.clauses };
  fail(`Unknown editor kind ${kind}`);
}

function documentFromModel(kind, model) {
  if (kind === "lora") return documentFromLora(model);
  if (kind === "theme") return documentFromTheme(model);
  if (kind === "enable") return documentFromEnable(model);
  fail(`Unknown editor kind ${kind}`);
}

function emitDocument(kind, checked) {
  if (kind === "lora") return emitLora(checked);
  if (kind === "theme") return emitTheme(checked);
  if (kind === "enable") return emitEnable(checked);
  fail(`Unknown editor kind ${kind}`);
}

function checkDocument(kind, data) {
  if (kind === "lora") return checkLoraLibrary(data);
  if (kind === "theme") return checkTheme(data);
  if (kind === "enable") return checkEnable(data);
  fail(`Unknown editor kind ${kind}`);
}

export function parseEditorDocument(kind, text) {
  let data;
  try {
    const source = String(text).replace(/^\uFEFF/, "");
    data = JSON.parse(source);
  } catch (exc) {
    return { ok: false, error: `Invalid JSON: ${exc.message}` };
  }
  try {
    if (!isObject(data)) fail("Document must be a JSON object.");
    const checked = checkDocument(kind, data);
    return { ok: true, model: editorFromChecked(kind, checked) };
  } catch (exc) {
    if (exc instanceof EditorModelError) return { ok: false, error: exc.message };
    return { ok: false, error: exc.message || String(exc) };
  }
}

export function commitModel(kind, model) {
  try {
    const checked = documentFromModel(kind, model);
    const doc = emitDocument(kind, checked);
    return { ok: true, json: JSON.stringify(doc, null, 2), doc, model: editorFromChecked(kind, checked) };
  } catch (exc) {
    if (exc instanceof EditorModelError) return { ok: false, error: exc.message };
    return { ok: false, error: exc.message || String(exc) };
  }
}

export function blankLora() {
  return { lora_id: "", name: "", strength_model: 0.8, strength_clip: 0.8, tags: [], enabled_default: true, meta: null };
}

export function blankOption() {
  return { option_id: "", label: "", description: "", tags: [] };
}

/** Display order: user options in array order, then None last. Array/prompt indexes are unchanged. */
export function optionDisplayOrder(options, noneOptionId) {
  const list = Array.isArray(options) ? options.filter(Boolean) : [];
  const noneId = String(noneOptionId || "").trim();
  const rest = [];
  const none = [];
  for (const option of list) {
    const id = String(option.option_id || "");
    const isNone = (noneId && id === noneId) || (!noneId && isNoneLikeOption(option));
    if (isNone) none.push(option);
    else rest.push(option);
  }
  return rest.concat(none);
}

/**
 * Append a new option after existing ones so None keeps its option_id and
 * array/prompt index when it sits in the middle. nextOptionId fills the
 * smallest free option_N and will not collide with None's id.
 */
export function addThemeOption(model) {
  if (!model || typeof model !== "object") return { ok: false, error: "invalid theme" };
  if (!Array.isArray(model.options)) model.options = [];
  assignOptionIds(model.options);
  ensureDefaultNoneOption(model);
  if (model.options.length >= MAX_OPTION_OUTPUTS) {
    return { ok: false, error: `cannot add an option; option outputs are capped at ${MAX_OPTION_OUTPUTS}` };
  }
  const existing = model.options.map((option) => option?.option_id).filter(Boolean);
  const option = blankOption();
  option.option_id = nextOptionId(existing);
  model.options.push(option);
  return { ok: true, model, option };
}

export function deleteThemeOption(model, optionId) {
  if (!model || !Array.isArray(model.options)) return { ok: false, error: "invalid theme" };
  ensureDefaultNoneOption(model);
  const noneId = String(model.none_option_id || "");
  if (!optionId || String(optionId) === noneId) {
    return { ok: false, error: "the None option cannot be deleted" };
  }
  const next = model.options.filter((option) => String(option?.option_id) !== String(optionId));
  if (next.length === model.options.length) return { ok: false, error: "option not found" };
  model.options = next;
  return { ok: true, model };
}

/** Move a non-None option among non-None slots. None stays at its array index. */
export function moveThemeOption(model, optionId, direction) {
  if (!model || !Array.isArray(model.options)) return { ok: false, moved: false };
  ensureDefaultNoneOption(model);
  const noneId = String(model.none_option_id || "");
  if (!optionId || String(optionId) === noneId) return { ok: false, moved: false, error: "the None option cannot be moved" };
  const options = model.options;
  const movable = [];
  options.forEach((option, index) => {
    if (String(option?.option_id || "") !== noneId) movable.push(index);
  });
  const pos = movable.findIndex((index) => String(options[index]?.option_id) === String(optionId));
  if (pos < 0) return { ok: false, moved: false, error: "option not found" };
  const swap = pos + (direction < 0 ? -1 : 1);
  if (swap < 0 || swap >= movable.length) return { ok: true, moved: false, model };
  const left = movable[pos];
  const right = movable[swap];
  const temp = options[left];
  options[left] = options[right];
  options[right] = temp;
  return { ok: true, moved: true, model };
}

export function blankClause() {
  return { theme_id: "", op: "includes_any", option_ids: [] };
}

export function emptyThemeModel() {
  return {
    version: 1,
    theme_id: "",
    title: "",
    instructions: "",
    select_mode: "single",
    options: [],
    none_option_id: "",
  };
}

export function emptyEnableModel() {
  return { version: 1, match: "any", clauses: [] };
}

export function splitList(text) {
  return String(text)
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item !== "");
}

/** Trim, drop empties, and dedupe tags (first spelling wins, case-insensitive). */
export function tokenizeTags(value) {
  const parts = Array.isArray(value)
    ? value.flatMap((item) => String(item ?? "").split(/[,\n]/))
    : String(value ?? "").split(/[,\n]/);
  const tags = [];
  const seen = new Set();
  for (const part of parts) {
    const tag = String(part).trim();
    if (!tag) continue;
    const key = tag.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    tags.push(tag);
  }
  return tags;
}

export function addTagToken(tags, text) {
  return tokenizeTags([...(Array.isArray(tags) ? tags : tokenizeTags(tags)), text]);
}

export function removeTagToken(tags, index) {
  const current = tokenizeTags(tags);
  if (!Number.isInteger(index) || index < 0 || index >= current.length) return current;
  return current.filter((_, itemIndex) => itemIndex !== index);
}

export function tagsToCommaString(tags) {
  return tokenizeTags(tags).join(", ");
}

export function normalizeLoraPath(name) {
  return String(name ?? "").trim().replace(/\\/g, "/");
}

export function isUsableLoraName(name) {
  const text = normalizeLoraPath(name);
  if (!text) return false;
  if (/^none$/i.test(text)) return false;
  return true;
}

export function loraNameFromMenuValue(value) {
  if (value == null) return "";
  if (typeof value === "string") return normalizeLoraPath(value);
  if (typeof value === "object") {
    if (value.has_submenu) return "";
    if (value.s1LoraName) return normalizeLoraPath(value.s1LoraName);
    if (value.value != null && typeof value.value !== "object") return normalizeLoraPath(value.value);
    const content = value.content != null ? String(value.content) : "";
    if (content.startsWith("📁")) return "";
    if (content) return normalizeLoraPath(content);
  }
  return normalizeLoraPath(String(value));
}

/**
 * One pick callback for a single chooser opening. LiteGraph 1.57.6
 * ContextMenu.addItem inner_onclick calls options.callback and then, if
 * the item is an object, value.callback. Unusable values (folders, None,
 * cancel) do not consume the shot so a later real pick still works.
 */
export function makeLoraChooserPickCallback(onPick) {
  let accepted = false;
  return function s1LoraChooserPick(value) {
    const picked = loraNameFromMenuValue(value);
    if (!isUsableLoraName(picked)) return;
    if (accepted) return;
    accepted = true;
    if (typeof onPick === "function") onPick(picked);
  };
}

/**
 * LiteGraph.ContextMenu 1.57.6 opens a submenu as
 * `new ContextMenu(submenu.options, { callback: submenu.callback, parentMenu })`.
 * It does not inherit the parent menu's options.callback, so a top-level
 * chooser callback never runs for a file inside a folder unless it is
 * copied onto every submenu.
 *
 * Copy the callback only onto submenu.callback (the menu-level
 * options.callback of the child menu). Do not also set item.callback on
 * leaves: inner_onclick would fire both and add two rows.
 */
export function withLoraChooserCallback(items, callback) {
  if (!Array.isArray(items)) return [];
  return items.map((item) => {
    if (!item || typeof item !== "object") return item;
    const next = { ...item };
    if (next.has_submenu || next.submenu) {
      const submenu = { ...(next.submenu || {}) };
      submenu.callback = callback;
      submenu.options = withLoraChooserCallback(submenu.options || [], callback);
      next.submenu = submenu;
    }
    if (next.callback === callback) delete next.callback;
    return next;
  });
}

/** Nested folder tree from LoRA paths like "Anima/sub/name.safetensors". */
export function buildLoraMenuTree(names) {
  const root = { folders: new Map(), files: [] };
  for (const name of names || []) {
    const text = String(name ?? "");
    if (!text) continue;
    const parts = text.split(/[/\\]/).filter((part) => part.length);
    if (parts.length <= 1) {
      root.files.push(text);
      continue;
    }
    let node = root;
    for (let index = 0; index < parts.length - 1; index += 1) {
      const key = parts[index];
      if (!node.folders.has(key)) node.folders.set(key, { folders: new Map(), files: [] });
      node = node.folders.get(key);
    }
    node.files.push(text);
  }
  return root;
}

function menuItemsFromLoraTree(node) {
  const items = [];
  const folderNames = [...node.folders.keys()].sort((left, right) => left.localeCompare(right));
  for (const folder of folderNames) {
    items.push({
      content: `📁 ${folder}`,
      has_submenu: true,
      submenu: { options: menuItemsFromLoraTree(node.folders.get(folder)), className: "dark" },
    });
  }
  const files = [...node.files].sort((left, right) => left.localeCompare(right));
  for (const full of files) {
    const base = full.split(/[/\\]/).pop();
    items.push({ content: base, value: full, s1LoraName: full });
  }
  return items;
}

/** LiteGraph.ContextMenu values: folders as submenus, leaves carry the full path. */
export function loraChooserMenuItems(names) {
  return menuItemsFromLoraTree(buildLoraMenuTree(names));
}

export function newLoraRowFromPick(name) {
  const picked = loraNameFromMenuValue(name);
  if (!isUsableLoraName(picked)) return null;
  const row = blankLora();
  row.name = picked;
  row.enabled_default = true;
  row.strength_model = 1;
  row.strength_clip = 1;
  return row;
}

/**
 * Pure chooser result: cancel/None adds nothing; a pick appends a default-on
 * strength 1.00 row; swap changes only the existing row's name.
 */
export function applyLoraChooserAction(loras, action, picked, index) {
  const list = Array.isArray(loras) ? loras.map((entry) => ({ ...(entry || {}) })) : [];
  const name = loraNameFromMenuValue(picked);
  if (action === "add") {
    const row = newLoraRowFromPick(name);
    if (!row) return { loras: list, changed: false };
    list.push(row);
    return { loras: list, changed: true, row };
  }
  if (action === "swap") {
    if (!Number.isInteger(index) || index < 0 || index >= list.length) {
      return { loras: list, changed: false };
    }
    if (!isUsableLoraName(name)) return { loras: list, changed: false };
    if (list[index].name === name) return { loras: list, changed: false };
    list[index].name = name;
    return { loras: list, changed: true };
  }
  return { loras: list, changed: false };
}

function uniqueStrings(value) {
  if (!Array.isArray(value)) return null;
  const seen = new Set();
  const names = [];
  for (const item of value) {
    if (typeof item !== "string" || item === "" || seen.has(item)) continue;
    seen.add(item);
    names.push(item);
  }
  return names;
}

export function loraNamesFromSpec(spec) {
  if (Array.isArray(spec)) {
    if (Array.isArray(spec[0])) return uniqueStrings(spec[0]);
    if (spec[0] === "COMBO" && Array.isArray(spec[1])) return uniqueStrings(spec[1]);
    if (spec[0] === "COMBO" && spec[1] && typeof spec[1] === "object" && Array.isArray(spec[1].options)) {
      return uniqueStrings(spec[1].options);
    }
    return null;
  }
  if (spec && typeof spec === "object") {
    if (Array.isArray(spec.options)) return uniqueStrings(spec.options);
    if (Array.isArray(spec.values)) return uniqueStrings(spec.values);
  }
  return null;
}

export function loraNamesFromNodeInfo(info) {
  if (!info || typeof info !== "object") return null;
  const input = info.input && typeof info.input === "object" ? info.input : null;
  const pools = input ? [input.required, input.optional] : [info.required, info.optional];
  for (const pool of pools) {
    if (!pool || typeof pool !== "object" || !Object.prototype.hasOwnProperty.call(pool, "lora_name")) continue;
    return loraNamesFromSpec(pool.lora_name);
  }
  return null;
}

export function loraNamesFromInfo(data) {
  if (!data || typeof data !== "object" || Array.isArray(data)) return null;
  for (const key of ["LoraLoader", "LoraLoaderModelOnly"]) {
    if (!data[key]) continue;
    const names = loraNamesFromNodeInfo(data[key]);
    if (names) return names;
  }
  if (data.input) return loraNamesFromNodeInfo(data);
  return null;
}

export function loraNamesFromModels(data) {
  if (!Array.isArray(data)) return null;
  return uniqueStrings(
    data.map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item.name === "string") return item.name;
      if (item && typeof item.filename === "string") return item.filename;
      return "";
    }),
  );
}


export const MAX_COLLECT_INPUTS = 16;
export const COLLECT_INPUT_NAMES = Array.from({ length: MAX_COLLECT_INPUTS }, (_, index) =>
  String.fromCharCode("a".charCodeAt(0) + index),
);
export const COLLECT_TYPE = "S1_DECISION";

function liveTargetSlots(node) {
  const live = new Set();
  eachGraphLink(node?.graph, (link) => {
    const parts = linkParts(link);
    if (!parts || !sameNodeId(parts.targetId, node.id)) return;
    const index = asSlot(parts.targetSlot);
    if (index == null || index < 0) return;
    live.add(index);
  });
  return live;
}

function inputHasLink(input, liveSlots, index) {
  if (!input) return false;
  if (input.link != null && input.link !== false) return true;
  return liveSlots.has(index);
}

/**
 * Plan Collect visibility: every connected socket stays visible, plus one
 * trailing empty socket. a remains visible even when nothing is wired so a
 * new node has somewhere to connect. Connected sockets are never hidden.
 */
export function planCollectInputs(node) {
  const names = COLLECT_INPUT_NAMES;
  const inputs = Array.isArray(node?.inputs) ? node.inputs : [];
  const liveSlots = liveTargetSlots(node);
  const byName = new Map();
  inputs.forEach((input, index) => {
    if (input?.name) byName.set(String(input.name), { input, index, live: inputHasLink(input, liveSlots, index) });
  });
  const connected = [];
  for (const name of names) {
    const row = byName.get(name);
    if (row?.live) connected.push(name);
  }
  const visible = new Set(connected);
  visible.add("a");
  const lastConnectedIndex = connected.length ? names.indexOf(connected[connected.length - 1]) : 0;
  const emptyIndex = Math.min(lastConnectedIndex + (connected.length ? 1 : 0), names.length - 1);
  visible.add(names[emptyIndex]);
  if (!connected.length) visible.add("a");
  return {
    names,
    visible: names.map((name) => visible.has(name)),
    connected,
    empty: names[emptyIndex],
  };
}

export function syncCollectInputs(node) {
  if (!node) return { ok: false };
  if (!Array.isArray(node.inputs)) node.inputs = [];
  const existing = new Map();
  const byName = new Map();
  const others = [];
  node.inputs.forEach((input, index) => {
    if (input && COLLECT_INPUT_NAMES.includes(input.name)) {
      byName.set(input.name, input);
      existing.set(input.name, index);
    } else if (input) {
      others.push(input);
    }
  });
  const planning = {
    ...node,
    inputs: COLLECT_INPUT_NAMES.map((name) => byName.get(name) || { name, type: COLLECT_TYPE, link: null }),
    graph: node.graph,
    id: node.id,
  };
  const plan = planCollectInputs(planning);
  const liveSlots = liveTargetSlots(node);
  const wanted = [];
  plan.names.forEach((name, index) => {
    const input = byName.get(name);
    const live = inputHasLink(input, liveSlots, existing.get(name) ?? index);
    if (live || plan.visible[index]) {
      if (input) input.hidden = false;
      wanted.push(name);
    }
  });
  const next = wanted.map((name) => {
    const input = byName.get(name) || { name, type: COLLECT_TYPE, link: null };
    input.type = COLLECT_TYPE;
    input.name = name;
    input.hidden = false;
    return input;
  });
  node.inputs = next.concat(others);
  // Remap target_slot for graph.links after reorder, using the same care as
  // orderThemePromptInputs: never assign input.link, only rewrite the slot index.
  if (node.graph) {
    node.inputs.forEach((input, index) => {
      const linkId = input?.link;
      if (linkId == null) return;
      const links = node.graph.links;
      const link = Array.isArray(links) ? links[linkId] : links?.get?.(linkId) ?? links?.[linkId];
      if (!link) return;
      if (Array.isArray(link)) link[4] = index;
      else {
        if ("target_slot" in link || !("targetSlot" in link)) link.target_slot = index;
        if ("targetSlot" in link) link.targetSlot = index;
      }
    });
  }
  return { ok: true, plan, visible: wanted };
}

function tagsFromLibraryJson(text) {
  try {
    const data = JSON.parse(String(text || "").replace(/^\uFEFF/, ""));
    const loras = data?.loras;
    if (!Array.isArray(loras)) return [];
    const tags = [];
    for (const entry of loras) {
      const list = entry?.tags;
      if (!Array.isArray(list)) continue;
      for (const tag of list) {
        if (typeof tag === "string" && tag.trim()) tags.push(tag.trim());
      }
    }
    return tags;
  } catch {
    return [];
  }
}

function tagsFromThemeJson(text) {
  try {
    const data = JSON.parse(String(text || "").replace(/^\uFEFF/, ""));
    const options = data?.options;
    if (!Array.isArray(options)) return [];
    const tags = [];
    for (const option of options) {
      const list = option?.tags;
      if (!Array.isArray(list)) continue;
      for (const tag of list) {
        if (typeof tag === "string" && tag.trim()) tags.push(tag.trim());
      }
    }
    return tags;
  } catch {
    return [];
  }
}

function widgetValueByName(node, name) {
  const widgets = node?.widgets || [];
  for (const widget of widgets) {
    if (widget?.name === name) {
      const value = widget.value;
      return typeof value === "string" ? value : value == null ? "" : String(value);
    }
  }
  return "";
}

export function collectGraphTags(graph, currentNode) {
  const tags = [];
  const seen = new Set();
  const add = (item) => {
    const tag = String(item || "").trim();
    if (!tag || seen.has(tag)) return;
    seen.add(tag);
    tags.push(tag);
  };
  const visit = (owner) => {
    const nodes = owner?._nodes || owner?.nodes || [];
    for (const node of nodes) {
      if (!node || node === currentNode) continue;
      const kind = node.comfyClass || node.constructor?.comfyClass || node.type || "";
      if (kind === "S1LoraLibrary") {
        tagsFromLibraryJson(widgetValueByName(node, "library_json")).forEach(add);
      } else if (kind === "S1ThemeRoot" || kind === "S1Theme") {
        tagsFromThemeJson(widgetValueByName(node, "theme_json")).forEach(add);
      }
      if (node.subgraph) visit(node.subgraph);
    }
  };
  visit(graph);
  return tags;
}
