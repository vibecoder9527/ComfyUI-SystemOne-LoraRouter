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

export function assignThemeDocument(model) {
  if (!model || typeof model !== "object" || Array.isArray(model)) return model;
  if (!idKept(model.theme_id)) model.theme_id = nextThemeId([]);
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

/** Visible slot label. A label and an id become "label (id)". */
export function optionOutputName(option) {
  const id = option && option.option_id != null ? String(option.option_id) : "";
  const label = option && option.label != null ? String(option.label).trim() : "";
  if (label && id) return `${label} (${id})`;
  return id || label;
}

/**
 * Plan the 32 option sockets for one theme document.
 * Invalid JSON returns ok:false and slots:null. The caller leaves outputs alone.
 */
export function planOptionOutputs(themeJson) {
  const text = typeof themeJson === "string" ? themeJson : JSON.stringify(themeJson ?? null);
  const parsed = parseEditorDocument("theme", text);
  if (!parsed.ok) return { ok: false, error: parsed.error, slots: null };
  const options = parsed.model.options || [];
  if (options.length > MAX_OPTION_OUTPUTS) {
    return {
      ok: false,
      error: `This theme has ${options.length} options. Option outputs are capped at ${MAX_OPTION_OUTPUTS}.`,
      slots: null,
    };
  }
  const slots = [];
  for (let index = 0; index < MAX_OPTION_OUTPUTS; index += 1) {
    if (index < options.length) {
      const option = options[index];
      slots.push({
        index,
        option_id: String(option.option_id || ""),
        name: optionOutputName(option),
        type: DECISION_TYPE,
        hidden: false,
      });
    } else {
      slots.push({ index, option_id: "", name: "", type: DECISION_TYPE, hidden: true });
    }
  }
  return { ok: true, slots, reportIndex: REPORT_OUTPUT_INDEX };
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
    return {
      id: link.id,
      originId: link.origin_id,
      originSlot: link.origin_slot,
      targetId: link.target_id,
      targetSlot: link.target_slot,
    };
  }
  return null;
}

function writeOriginSlot(link, slot) {
  if (Array.isArray(link)) link[2] = slot;
  else if (link && typeof link === "object") link.origin_slot = slot;
}

function eachGraphLink(graph, visit) {
  const links = graph?.links;
  if (!links) return;
  if (Array.isArray(links)) {
    for (let index = 0; index < links.length; index += 1) {
      if (links[index]) visit(links[index], index, "array");
    }
    return;
  }
  for (const key of Object.keys(links)) {
    if (links[key]) visit(links[key], key, "map");
  }
}

function nodeById(graph, id) {
  if (typeof graph?.getNodeById === "function") return graph.getNodeById(id);
  const nodes = graph?._nodes || graph?.nodes || [];
  return nodes.find((node) => node && node.id === id) || null;
}

function dropGraphLink(graph, link, key, kind) {
  if (!graph?.links) return;
  const parts = linkParts(link);
  if (kind === "array") graph.links[key] = null;
  else delete graph.links[key];
  if (!parts) return;
  const target = nodeById(graph, parts.targetId);
  const input = target?.inputs?.[parts.targetSlot];
  if (!input) return;
  if (input.link === parts.id) input.link = null;
  if (Array.isArray(input.links)) input.links = input.links.filter((item) => item !== parts.id);
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
 * move links. A later sync moves graph.links origin_slot to the option's new
 * index and drops a link whose option disappeared. Links on the report socket
 * (index 32) stay put. A report_json name alone does not count as a prior sync.
 */
export function relinkOptionSlots(node, slots) {
  if (!node || !Array.isArray(slots) || slots.length < MAX_OPTION_OUTPUTS) {
    return { ok: false, first: true, moved: 0, dropped: 0 };
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
  if (!first && node.graph) {
    const nextIndex = new Map();
    slots.forEach((slot, index) => {
      if (slot?.option_id && !slot.hidden) nextIndex.set(String(slot.option_id), index);
    });
    const pending = [];
    eachGraphLink(node.graph, (link, key, kind) => {
      const parts = linkParts(link);
      if (!parts || parts.originId !== node.id) return;
      if (typeof parts.originSlot !== "number" || parts.originSlot >= REPORT_OUTPUT_INDEX) return;
      const optionId = previous[parts.originSlot] || "";
      if (!optionId) return;
      pending.push({
        link,
        key,
        kind,
        id: parts.id,
        from: parts.originSlot,
        to: nextIndex.has(optionId) ? nextIndex.get(optionId) : -1,
      });
    });
    for (const item of pending) {
      const fromOutput = outputs[item.from];
      if (fromOutput && Array.isArray(fromOutput.links)) {
        fromOutput.links = fromOutput.links.filter((id) => id !== item.id);
      }
      if (item.to < 0) {
        dropGraphLink(node.graph, item.link, item.key, item.kind);
        dropped += 1;
        continue;
      }
      writeOriginSlot(item.link, item.to);
      const dest = ensureOutput(outputs, item.to, DECISION_TYPE);
      if (!Array.isArray(dest.links)) dest.links = dest.links == null ? [] : [dest.links];
      if (!dest.links.includes(item.id)) dest.links.push(item.id);
      if (item.from !== item.to) moved += 1;
    }
  }
  for (let index = 0; index < MAX_OPTION_OUTPUTS; index += 1) {
    const slot = slots[index];
    const output = ensureOutput(outputs, index, DECISION_TYPE);
    output.name = slot.hidden ? "" : slot.name;
    output.label = output.name;
    output.type = DECISION_TYPE;
    output.hidden = Boolean(slot.hidden);
    output.s1OptionId = slot.option_id || "";
  }
  const report = ensureOutput(outputs, REPORT_OUTPUT_INDEX, "STRING");
  if (!report.name) report.name = "report_json";
  if (!report.type || report.type === DECISION_TYPE) report.type = "STRING";
  report.hidden = false;
  return { ok: true, first, moved, dropped };
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
