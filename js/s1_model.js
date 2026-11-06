// Editor model for the three SystemOne JSON documents.
// Field rules match schema/types.py. This file does not import ComfyUI.

export const SELECT_MODES = ["single", "multi"];
export const WHEN_OPS = ["eq", "neq", "includes_any", "includes_all", "skipped", "answered"];
export const ACTION_TYPES = [
  "enable_step",
  "disable_step",
  "rewrite_options",
  "rewrite_instructions",
  "set_select_mode",
];

const BARE_OPS = new Set(["skipped", "answered"]);
const REWRITE_KEYS = ["keep_option_ids", "add_options", "remove_option_ids", "patch_bindings"];

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

function optionalFloat(data, key, path) {
  if (!Object.prototype.hasOwnProperty.call(data, key) || data[key] === null) return null;
  return finiteNumber(data[key], `${path}.${key}`);
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

function checkBinding(data, path) {
  if (!isObject(data)) fail(`${path} must be an object`);
  rejectUnknown(data, ["lora_id", "strength_model", "strength_clip"], path);
  const out = { lora_id: requireId(data.lora_id, `${path}.lora_id`) };
  const strengthModel = optionalFloat(data, "strength_model", path);
  const strengthClip = optionalFloat(data, "strength_clip", path);
  if (strengthModel !== null) out.strength_model = strengthModel;
  if (strengthClip !== null) out.strength_clip = strengthClip;
  return out;
}

function checkOption(data, path, seen) {
  if (!isObject(data)) fail(`${path} must be an object`);
  rejectUnknown(data, ["option_id", "label", "description", "lora_bindings"], path);
  const optionId = requireId(data.option_id, `${path}.option_id`);
  if (seen.has(optionId)) fail(`${path}: duplicate option_id ${optionId}`);
  seen.add(optionId);
  const rawBindings = data.lora_bindings === undefined ? [] : data.lora_bindings;
  if (!Array.isArray(rawBindings)) fail(`${path}.lora_bindings must be a list`);
  return {
    option_id: optionId,
    label: requireText(data.label, `${path}.label`, true),
    description: requireText(data.description, `${path}.description`, true),
    lora_bindings: rawBindings.map((item, index) => checkBinding(item, `${path}.lora_bindings[${index}]`)),
  };
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

function checkTheme(data, path) {
  if (!isObject(data)) fail(`${path} must be an object`);
  rejectUnknown(
    data,
    ["theme_id", "title", "instructions", "select_mode", "options", "fallback_option_id", "none_option_id"],
    path,
  );
  if (!Array.isArray(data.options)) fail(`${path}.options must be a list`);
  const seen = new Set();
  const options = data.options.map((item, index) => checkOption(item, `${path}.options[${index}]`, seen));
  const known = new Set(options.map((option) => option.option_id));
  const fallback = optionalId(data, "fallback_option_id", path);
  const noneId = optionalId(data, "none_option_id", path);
  if (fallback !== null && !known.has(fallback)) {
    fail(`${path}: fallback_option_id ${fallback} is not an option of this theme`);
  }
  if (noneId !== null && !known.has(noneId)) {
    fail(`${path}: none_option_id ${noneId} is not an option of this theme`);
  }
  return {
    theme_id: requireId(data.theme_id, `${path}.theme_id`),
    title: requireText(data.title, `${path}.title`),
    instructions: requireText(data.instructions, `${path}.instructions`),
    select_mode: requireChoice(data.select_mode, SELECT_MODES, `${path}.select_mode`),
    options,
    fallback_option_id: fallback,
    none_option_id: noneId,
  };
}

function optionalId(data, key, path) {
  if (!Object.prototype.hasOwnProperty.call(data, key) || data[key] === null) return null;
  return requireId(data[key], `${path}.${key}`);
}

function checkWhen(data, path) {
  if (!isObject(data)) fail(`${path} must be an object`);
  rejectUnknown(data, ["step_id", "op", "option_ids"], path);
  const op = requireChoice(data.op, WHEN_OPS, `${path}.op`);
  let optionIds = [];
  if (BARE_OPS.has(op)) {
    if (Object.prototype.hasOwnProperty.call(data, "option_ids") && data.option_ids != null && !(Array.isArray(data.option_ids) && data.option_ids.length === 0)) {
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
  return { step_id: requireId(data.step_id, `${path}.step_id`), op, option_ids: optionIds };
}

function checkAction(data, path) {
  if (!isObject(data)) fail(`${path} must be an object`);
  if (typeof data.type !== "string" || !ACTION_TYPES.includes(data.type)) {
    fail(`${path}.type must be one of: ${ACTION_TYPES.join(", ")}`);
  }
  if (data.type === "enable_step" || data.type === "disable_step") {
    rejectUnknown(data, ["type"], path);
    return { type: data.type };
  }
  if (data.type === "rewrite_instructions") {
    rejectUnknown(data, ["type", "instructions"], path);
    return { type: data.type, instructions: requireText(data.instructions, `${path}.instructions`) };
  }
  if (data.type === "set_select_mode") {
    rejectUnknown(data, ["type", "select_mode"], path);
    return { type: data.type, select_mode: requireChoice(data.select_mode, SELECT_MODES, `${path}.select_mode`) };
  }
  rejectUnknown(data, ["type", ...REWRITE_KEYS], path);
  const out = { type: "rewrite_options" };
  if (Object.prototype.hasOwnProperty.call(data, "keep_option_ids")) {
    out.keep_option_ids = stringList(data.keep_option_ids, `${path}.keep_option_ids`, { ids: true });
  }
  if (Object.prototype.hasOwnProperty.call(data, "remove_option_ids")) {
    out.remove_option_ids = stringList(data.remove_option_ids, `${path}.remove_option_ids`, { ids: true });
  }
  if (Object.prototype.hasOwnProperty.call(data, "add_options")) {
    if (!Array.isArray(data.add_options)) fail(`${path}.add_options must be a list`);
    const seen = new Set();
    out.add_options = data.add_options.map((item, index) => checkOption(item, `${path}.add_options[${index}]`, seen));
  }
  if (Object.prototype.hasOwnProperty.call(data, "patch_bindings")) {
    if (!isObject(data.patch_bindings)) fail(`${path}.patch_bindings must be an object`);
    const patch = {};
    for (const [optionId, rawBindings] of Object.entries(data.patch_bindings)) {
      if (typeof optionId !== "string" || optionId === "" || /\s/.test(optionId)) {
        fail(`${path}.patch_bindings keys must be option ids without whitespace`);
      }
      if (!Array.isArray(rawBindings)) fail(`${path}.patch_bindings[${optionId}] must be a list of bindings`);
      patch[optionId] = rawBindings.map((item, index) => checkBinding(item, `${path}.patch_bindings.${optionId}[${index}]`));
    }
    out.patch_bindings = patch;
  }
  return out;
}

function checkDependency(data, path) {
  if (!isObject(data)) fail(`${path} must be an object`);
  rejectUnknown(data, ["when", "actions"], path);
  if (!Object.prototype.hasOwnProperty.call(data, "when")) fail(`${path}: missing when`);
  if (!Object.prototype.hasOwnProperty.call(data, "actions")) fail(`${path}: missing actions`);
  if (!Array.isArray(data.actions)) fail(`${path}.actions must be a list`);
  return {
    when: checkWhen(data.when, `${path}.when`),
    actions: data.actions.map((item, index) => checkAction(item, `${path}.actions[${index}]`)),
  };
}

function checkStep(data, path) {
  if (!isObject(data)) fail(`${path} must be an object`);
  rejectUnknown(data, ["step_id", "theme_id", "enabled_by_default", "dependencies"], path);
  const rawDeps = data.dependencies === undefined ? [] : data.dependencies;
  if (!Array.isArray(rawDeps)) fail(`${path}.dependencies must be a list`);
  const enabled = Object.prototype.hasOwnProperty.call(data, "enabled_by_default")
    ? requireBool(data.enabled_by_default, `${path}.enabled_by_default`)
    : true;
  return {
    step_id: requireId(data.step_id, `${path}.step_id`),
    theme_id: requireId(data.theme_id, `${path}.theme_id`),
    enabled_by_default: enabled,
    dependencies: rawDeps.map((item, index) => checkDependency(item, `${path}.dependencies[${index}]`)),
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

function checkThemeLibrary(data) {
  if (!isObject(data)) fail("theme library must be an object");
  rejectUnknown(data, ["version", "themes"], "theme library");
  readVersion(data, "theme library");
  if (!Array.isArray(data.themes)) fail("theme library: themes must be a list");
  const seen = new Set();
  const themes = data.themes.map((item, index) => {
    const theme = checkTheme(item, `themes[${index}]`);
    if (seen.has(theme.theme_id)) fail(`themes[${index}]: duplicate theme_id ${theme.theme_id}`);
    seen.add(theme.theme_id);
    return theme;
  });
  return { version: 1, themes };
}

function checkSequence(data) {
  if (!isObject(data)) fail("sequence must be an object");
  rejectUnknown(data, ["version", "steps"], "sequence");
  readVersion(data, "sequence");
  if (!Array.isArray(data.steps)) fail("sequence: steps must be a list");
  const seen = new Set();
  const steps = data.steps.map((item, index) => {
    const step = checkStep(item, `steps[${index}]`);
    if (seen.has(step.step_id)) fail(`steps[${index}]: duplicate step_id ${step.step_id}`);
    seen.add(step.step_id);
    return step;
  });
  return { version: 1, steps };
}

function actionToEditor(action) {
  if (action.type === "rewrite_options") {
    const extra = {};
    for (const key of REWRITE_KEYS) {
      if (Object.prototype.hasOwnProperty.call(action, key)) extra[key] = action[key];
    }
    return { type: action.type, rewrite_json: JSON.stringify(extra, null, 2) };
  }
  if (action.type === "rewrite_instructions") return { type: action.type, instructions: action.instructions };
  if (action.type === "set_select_mode") return { type: action.type, select_mode: action.select_mode };
  return { type: action.type };
}

function dependencyToEditor(dependency) {
  return {
    when: {
      step_id: dependency.when.step_id,
      op: dependency.when.op,
      option_ids: dependency.when.option_ids.slice(),
    },
    actions: dependency.actions.map(actionToEditor),
  };
}

function libraryToEditor(checked, key) {
  return { version: 1, [key]: checked[key] };
}

function sequenceToEditor(checked) {
  return {
    version: 1,
    steps: checked.steps.map((step) => ({
      step_id: step.step_id,
      theme_id: step.theme_id,
      enabled_by_default: step.enabled_by_default,
      dependencies: step.dependencies.map(dependencyToEditor),
    })),
  };
}

function bindingFromEditor(binding, path) {
  const out = { lora_id: binding?.lora_id ?? "" };
  const strengthModel = numberFromEditor(binding?.strength_model, `${path}.strength_model`, false);
  const strengthClip = numberFromEditor(binding?.strength_clip, `${path}.strength_clip`, false);
  if (strengthModel !== null) out.strength_model = strengthModel;
  if (strengthClip !== null) out.strength_clip = strengthClip;
  return out;
}

function optionFromEditor(option, path) {
  const bindings = Array.isArray(option?.lora_bindings) ? option.lora_bindings : [];
  return {
    option_id: option?.option_id ?? "",
    label: option?.label ?? "",
    description: option?.description ?? "",
    lora_bindings: bindings.map((binding, index) => bindingFromEditor(binding, `${path}.lora_bindings[${index}]`)),
  };
}

function actionFromEditor(action, path) {
  const type = action?.type;
  if (type === "enable_step" || type === "disable_step") return { type };
  if (type === "rewrite_instructions") return { type, instructions: action.instructions ?? "" };
  if (type === "set_select_mode") return { type, select_mode: action.select_mode ?? "" };
  if (type === "rewrite_options") {
    let extra;
    try {
      extra = JSON.parse(action.rewrite_json?.trim() ? action.rewrite_json : "{}");
    } catch (exc) {
      fail(`${path}: rewrite_options JSON is invalid (${exc.message})`);
    }
    if (!isObject(extra)) fail(`${path}: rewrite_options must be a JSON object`);
    delete extra.type;
    return { type, ...extra };
  }
  return { type: type ?? "" };
}

function documentFromLora(model) {
  const loras = (model?.loras || []).map((entry, index) => {
    const path = `loras[${index}]`;
    const out = {
      lora_id: entry.lora_id ?? "",
      name: entry.name ?? "",
      strength_model: numberFromEditor(entry.strength_model, `${path}.strength_model`, true),
      strength_clip: numberFromEditor(entry.strength_clip, `${path}.strength_clip`, true),
    };
    if (Array.isArray(entry.tags) && entry.tags.length) out.tags = entry.tags;
    if (entry.enabled_default === false) out.enabled_default = false;
    if (entry.meta && isObject(entry.meta) && Object.keys(entry.meta).length) out.meta = entry.meta;
    return out;
  });
  return checkLoraLibrary({ version: 1, loras });
}

function documentFromTheme(model) {
  const themes = (model?.themes || []).map((theme) => ({
    theme_id: theme.theme_id ?? "",
    title: theme.title ?? "",
    instructions: theme.instructions ?? "",
    select_mode: theme.select_mode ?? "",
    options: (theme.options || []).map((option, index) => optionFromEditor(option, `options[${index}]`)),
    fallback_option_id: blankToNull(theme.fallback_option_id),
    none_option_id: blankToNull(theme.none_option_id),
  }));
  return checkThemeLibrary({ version: 1, themes });
}

function documentFromSequence(model) {
  const steps = (model?.steps || []).map((step, stepIndex) => ({
    step_id: step.step_id ?? "",
    theme_id: step.theme_id ?? "",
    enabled_by_default: step.enabled_by_default !== false,
    dependencies: (step.dependencies || []).map((dependency, depIndex) => ({
      when: {
        step_id: dependency.when?.step_id ?? "",
        op: dependency.when?.op ?? "",
        ...(BARE_OPS.has(dependency.when?.op) ? {} : { option_ids: dependency.when?.option_ids || [] }),
      },
      actions: (dependency.actions || []).map((action, actionIndex) =>
        actionFromEditor(action, `steps[${stepIndex}].dependencies[${depIndex}].actions[${actionIndex}]`),
      ),
    })),
  }));
  return checkSequence({ version: 1, steps });
}

function blankToNull(value) {
  if (value === undefined || value === null || value === "") return null;
  return value;
}

function emitWhen(when) {
  const out = { step_id: when.step_id, op: when.op };
  if (!BARE_OPS.has(when.op)) out.option_ids = when.option_ids;
  return out;
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
  return {
    version: 1,
    themes: checked.themes.map((theme) => {
      const out = {
        theme_id: theme.theme_id,
        title: theme.title,
        instructions: theme.instructions,
        select_mode: theme.select_mode,
        options: theme.options,
      };
      if (theme.fallback_option_id) out.fallback_option_id = theme.fallback_option_id;
      if (theme.none_option_id) out.none_option_id = theme.none_option_id;
      return out;
    }),
  };
}

function emitSequence(checked) {
  return {
    version: 1,
    steps: checked.steps.map((step) => ({
      step_id: step.step_id,
      theme_id: step.theme_id,
      enabled_by_default: step.enabled_by_default,
      dependencies: step.dependencies.map((dependency) => ({
        when: emitWhen(dependency.when),
        actions: dependency.actions,
      })),
    })),
  };
}

function emitDocument(kind, checked) {
  if (kind === "lora") return emitLora(checked);
  if (kind === "theme") return emitTheme(checked);
  return emitSequence(checked);
}

function editorFromChecked(kind, checked) {
  if (kind === "lora") return libraryToEditor(checked, "loras");
  if (kind === "theme") return libraryToEditor(checked, "themes");
  if (kind === "sequence") return sequenceToEditor(checked);
  fail(`Unknown editor kind ${kind}`);
}

function documentFromModel(kind, model) {
  if (kind === "lora") return documentFromLora(model);
  if (kind === "theme") return documentFromTheme(model);
  if (kind === "sequence") return documentFromSequence(model);
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
    const checked =
      kind === "lora" ? checkLoraLibrary(data) : kind === "theme" ? checkThemeLibrary(data) : kind === "sequence" ? checkSequence(data) : fail(`Unknown editor kind ${kind}`);
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

export function blankBinding() {
  return { lora_id: "", strength_model: "", strength_clip: "" };
}

export function blankOption() {
  return { option_id: "", label: "", description: "", lora_bindings: [] };
}

export function blankTheme() {
  return {
    theme_id: "",
    title: "",
    instructions: "",
    select_mode: "single",
    options: [],
    fallback_option_id: "",
    none_option_id: "",
  };
}

export function blankAction(type = "enable_step") {
  if (type === "rewrite_instructions") return { type, instructions: "" };
  if (type === "set_select_mode") return { type, select_mode: "single" };
  if (type === "rewrite_options") return { type, rewrite_json: "{}" };
  return { type: type === "disable_step" ? "disable_step" : "enable_step" };
}

export function blankDependency() {
  return { when: { step_id: "", op: "includes_any", option_ids: [] }, actions: [blankAction("enable_step")] };
}

export function blankStep() {
  return { step_id: "", theme_id: "", enabled_by_default: true, dependencies: [] };
}

export function emptyModel(kind) {
  if (kind === "lora") return { version: 1, loras: [] };
  if (kind === "theme") return { version: 1, themes: [] };
  return { version: 1, steps: [] };
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

// Stock Lora Loader publishes its file list as the lora_name combo on
// /object_info. An empty array means the list was present and had no files.
// null means this payload has no recognizable list.
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
