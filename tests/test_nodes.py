"""Node registration, widget order, mocked runs, and editor invariants."""

from __future__ import annotations

import importlib
import inspect
import json
import shutil
import subprocess
import sys
import unittest
from unittest import mock

from tests.harness import (
    APPLY,
    CLIENT,
    ENGINE,
    PACKAGE_NAME,
    PKG,
    ROOT,
    TYPES,
    CountingClient,
    FakeHTTPResponse,
    as_payload,
    canned_urlopen,
    lora_entries,
    option,
    payload_from_request,
    read_example,
    run_theme,
    theme_doc,
)

BLOCKER = importlib.import_module(PACKAGE_NAME + ".schema.blocker")


JS_MODEL = r"""
import {
  assignLoraIds,
  assignOptionIds,
  assignThemeDocument,
  blankClause,
  blankLora,
  blankOption,
  commitModel,
  emptyThemeModel,
  fieldPathsFromError,
  loraNamesFromInfo,
  loraNamesFromModels,
  isAutoThemeId,
  nextLoraId,
  nextOptionId,
  nextThemeId,
  parseEditorDocument,
  planOptionOutputs,
  planThemeIds,
  optionOutputName,
  optionDisplayText,
  optionOutputLabels,
  relabelLegacyDefaultNoneOption,
  LEGACY_DEFAULT_NONE_TEXT,
  relinkOptionSlots,
  orderThemePromptInputs,
  MAX_OPTION_OUTPUTS,
  ensureDefaultNoneOption,
  isNoneLikeOption,
  DEFAULT_NONE_LABEL,
  syncCollectInputs,
  collectGraphTags,
  expandOptionOutputs,
  compactOptionOutputs,
  REPORT_OUTPUT_INDEX,
  optionDisplayOrder,
  addThemeOption,
  deleteThemeOption,
  moveThemeOption,
  tokenizeTags,
  addTagToken,
  removeTagToken,
  tagsToCommaString,
  parseTagToken,
  formatTagToken,
  formatTagChipLabel,
  normalizeLibraryTags,
  clampLoraStrength,
  buildLoraMenuTree,
  loraChooserMenuItems,
  applyLoraChooserAction,
  newLoraRowFromPick,
  isUsableLoraName,
  withLoraChooserCallback,
  makeLoraChooserPickCallback,
  normalizeLoraPath,
  loraNameFromMenuValue,
} from "./js/s1_model.js";
import { nextEditorNodeSize, applyEditorNodeSize, installEditorSizeGuard, measureHostHeight } from "./js/s1_node_size.js";
import {
  bindRowContextMenu,
  stopRowContextMenuEvent,
  isRightClickEvent,
  shouldSuppressNativeNodeMenu,
  hitTestNodeRows,
  registerRowMenuElement,
  clearRowMenuElements,
  installNativeNodeMenuSuppress,
} from "./js/s1_row_menu.js";

function assert(cond, message) {
  if (!cond) {
    console.error(message);
    process.exit(1);
  }
}

assert(nextLoraId([]) === "lora_1", "empty lora");
assert(nextLoraId(["lora_1", "lora_3"]) === "lora_2", "lora gap");
assert(nextLoraId(["style_anime_v3", "lora_1"]) === "lora_2", "manual lora");
assert(nextThemeId([]) === "theme_1", "empty theme");
assert(nextThemeId(["art_style"]) === "theme_1", "manual theme is not theme_N");
assert(nextOptionId(["option_1", "anime"]) === "option_2", "option gap");
assert(blankLora().lora_id === "", "blank lora id");
assert(blankOption().option_id === "", "blank option id");
assert(blankClause().op === "includes_any", "blank clause");
assert(!Object.prototype.hasOwnProperty.call(emptyThemeModel(), "fallback_option_id"), "no fallback");

const model = {
  loras: [
    { lora_id: "", name: "new.safetensors", strength_model: 0.2, strength_clip: 0.9 },
    { lora_id: "style_anime_v3", name: "a.safetensors", strength_model: 0.8, strength_clip: 0.4 },
    { lora_id: "lora_1", name: "b.safetensors", strength_model: 0.5, strength_clip: 0.5 },
    blankLora(),
    { lora_id: "   ", name: "blank.safetensors", strength_model: 1, strength_clip: 1 },
  ],
};
assignLoraIds(model);
assert(model.loras[0].lora_id === "lora_2", "blank skips lora_1");
assert(model.loras[1].lora_id === "style_anime_v3", "manual kept");
assert(model.loras[1].strength_clip === 0.4, "assign does not rewrite strength");

const applied = commitModel("lora", {
  loras: [
    { lora_id: "style_anime_v3", name: "a.safetensors", strength_model: 0.85, strength_clip: 0.2, tags: ["style"], enabled_default: false, meta: { note: "x" } },
    { lora_id: "", name: "new.safetensors", strength: "0.6", strength_model: 0.1, strength_clip: 0.1 },
    { name: "also.safetensors", strength_model: 0.3, strength_clip: 0.9 },
  ],
});
assert(applied.ok, applied.error || "lora commit failed");
assert(applied.doc.loras[0].strength_model === 0.85 && applied.doc.loras[0].strength_clip === 0.85, "strength_model copied");
assert(applied.doc.loras[1].strength_model === 0.6 && applied.doc.loras[1].strength_clip === 0.6, "editor strength");
assert(applied.doc.loras[2].lora_id === "lora_2", "missing id filled");
for (const entry of applied.doc.loras) {
  assert(!Object.prototype.hasOwnProperty.call(entry, "strength"), "no strength key");
}
assert(!applied.json.includes('\n    "strength":'), "pretty json has no strength");

const theme = commitModel("theme", {
  theme_id: "",
  title: "A",
  instructions: "i",
  select_mode: "single",
  options: [
    { option_id: "anime", label: "a", description: "", tags: ["style_anime"] },
    { option_id: "", label: "b", description: "" },
    { option_id: "option_1", label: "c", description: "" },
  ],
});
assert(theme.ok, theme.error || "theme commit failed");
assert(theme.doc.theme_id === "theme_1", "one document fills theme_1");
assert(theme.doc.options[0].option_id === "anime", "manual option kept");
assert(theme.doc.options[0].tags[0] === "style_anime", "tags kept");
assert(theme.doc.options[1].option_id === "option_2", "blank option skips option_1");
assert(theme.doc.options[2].option_id === "option_1", "option_1 kept");
assert(!JSON.stringify(theme.doc).includes("lora_bindings"), "theme json has no bindings");

const manual = commitModel("theme", {
  theme_id: "art_style",
  title: "t",
  instructions: "i",
  select_mode: "single",
  none_option_id: "none",
  options: [
    { option_id: "anime", label: "a", description: "", tags: ["style_anime"] },
    { option_id: "none", label: "n", description: "", tags: ["should_not_apply"] },
  ],
});
assert(manual.ok, manual.error || "manual theme failed");
assert(manual.doc.theme_id === "art_style", "manual theme id kept");
assert(manual.doc.none_option_id === "none", "none kept");

const stale = parseEditorDocument("theme", JSON.stringify({
  theme_id: "art_style",
  title: "t",
  instructions: "i",
  select_mode: "single",
  fallback_option_id: "anime",
  options: [{ option_id: "anime", label: "a", description: "" }],
}));
assert(!stale.ok, "fallback rejected");
assert(String(stale.error).includes("fallback_option_id was removed and is not applied"), stale.error || "");

const library = parseEditorDocument("theme", JSON.stringify({ themes: [] }));
assert(!library.ok, "theme library rejected");
assert(String(library.error).includes("one theme"), library.error || "");

const bindings = parseEditorDocument("theme", JSON.stringify({
  theme_id: "t",
  title: "t",
  instructions: "i",
  select_mode: "single",
  options: [{ option_id: "a", label: "a", description: "", lora_bindings: [] }],
}));
assert(!bindings.ok, "bindings rejected");
assert(String(bindings.error).includes("lora_bindings was removed"), bindings.error || "");

const bom = parseEditorDocument("enable", "\uFEFF" + JSON.stringify({ match: "any", clauses: [] }));
assert(bom.ok, bom.error || "bom enable");

const enable = commitModel("enable", {
  match: "all",
  clauses: [{ theme_id: "art_style", op: "includes_any", option_ids: "anime, realistic" }],
});
assert(enable.ok, enable.error || "enable commit");
assert(enable.doc.clauses[0].option_ids.join(",") === "anime,realistic", "option ids split");
const bare = commitModel("enable", { clauses: [{ theme_id: "art_style", op: "skipped" }] });
assert(bare.ok, bare.error || "bare op");
assert(!Object.prototype.hasOwnProperty.call(bare.doc.clauses[0], "option_ids"), "bare op omits option ids");
const badBare = parseEditorDocument("enable", JSON.stringify({
  clauses: [{ theme_id: "art_style", op: "skipped", option_ids: ["anime"] }],
}));
assert(!badBare.ok, badBare.error || "skipped rejects option ids");

assert(!commitModel("theme", emptyThemeModel()).ok, "empty title is not written");
const perTheme = [{ option_id: "" }, { option_id: "anime" }];
assignOptionIds(perTheme);
assignOptionIds([{ option_id: "" }]);
assert(perTheme[0].option_id === "option_1", "option ids stay in one list");
const single = { theme_id: "  ", title: "T", options: [{ option_id: "" }] };
assignThemeDocument(single);
assert(single.theme_id === "theme_1", "blank theme id is theme_1");
assert(single.options[0].option_id === "option_1", "blank option filled");

assert(JSON.stringify(fieldPathsFromError("options[1]: duplicate option_id option_1")) === JSON.stringify(["options.1", "options.1.option_id"]), "option path");
assert(JSON.stringify(fieldPathsFromError("loras[0]: duplicate lora_id lora_1")) === JSON.stringify(["loras.0", "loras.0.lora_id"]), "lora path");
assert(JSON.stringify(fieldPathsFromError("theme: none_option_id foo is not an option of this theme")) === JSON.stringify(["none_option_id"]), "none path");
assert(JSON.stringify(fieldPathsFromError("clauses[0]: op eq requires exactly one option_id")) === JSON.stringify(["clauses.0", "clauses.0.option_ids"]), "clause path");
assert(JSON.stringify(fieldPathsFromError("Invalid JSON: nope")) === "[]", "unmapped");

const wrapped = { LoraLoader: { input: { required: { lora_name: [["a.safetensors", "sub/b.safetensors", "a.safetensors"], {}] } } } };
assert(JSON.stringify(loraNamesFromInfo(wrapped)) === JSON.stringify(["a.safetensors", "sub/b.safetensors"]), "wrapped");
const direct = { input: { required: { lora_name: [["direct.safetensors"]] } } };
assert(JSON.stringify(loraNamesFromInfo(direct)) === JSON.stringify(["direct.safetensors"]), "direct");
assert(loraNamesFromInfo(null) === null, "null info");
assert(JSON.stringify(loraNamesFromModels(["m.safetensors", { name: "n.safetensors" }, { filename: "o.safetensors" }, 3])) === JSON.stringify(["m.safetensors", "n.safetensors", "o.safetensors"]), "models");
assert(loraNamesFromModels({ files: [] }) === null, "models object");

assert(isAutoThemeId("theme_1") && isAutoThemeId("theme_12"), "auto ids");
assert(!isAutoThemeId("theme_01") && !isAutoThemeId("theme_0") && !isAutoThemeId("art_style") && !isAutoThemeId("Theme_1"), "not auto");

function themeText(id, title) {
  return JSON.stringify({
    version: 1,
    theme_id: id,
    title: title || "T",
    instructions: "I",
    select_mode: "single",
    options: [],
  });
}
const emptyEnable = JSON.stringify({ version: 1, match: "any", clauses: [] });
const watchArt = JSON.stringify({
  version: 1,
  match: "any",
  clauses: [{ theme_id: "art_style", op: "includes_any", option_ids: ["anime"] }],
});
const watchTheme1 = JSON.stringify({
  version: 1,
  match: "any",
  clauses: [{ theme_id: "theme_1", op: "eq", option_ids: ["yes"] }],
});

const created = planThemeIds([
  { key: "n1", origin: "new", themeJson: themeText("theme_1", "A"), enableJson: emptyEnable },
  { key: "n2", origin: "new", themeJson: themeText("theme_1", "B"), enableJson: watchTheme1 },
  { key: "n3", origin: "duplicate", themeJson: themeText("theme_1", "C"), enableJson: watchTheme1 },
]);
assert(created.conflicts.length === 0, "new nodes do not conflict");
assert(created.assignments.map((item) => item.themeId).join(",") === "theme_1,theme_2,theme_3", "stable new ids");
assert(created.assignments[0].changed === false, "first theme_1 stays");
assert(created.assignments[1].changed === true && created.assignments[2].changed === true, "later copies change");
assert(created.assignments[1].enableJson === watchTheme1 && created.assignments[2].enableJson === watchTheme1, "enable not rewritten");
assert(created.assignments[1].enableJson.includes('"theme_1"'), "clause still names theme_1");
assert(!created.assignments[2].enableJson.includes("theme_3"), "clause does not follow the copy");
const again = planThemeIds(created.assignments.map((item) => ({
  key: item.key,
  origin: "new",
  themeJson: item.themeJson,
  enableJson: item.enableJson,
})));
assert(again.assignments.every((item) => item.changed === false), "second pass is a no-op");
assert(again.assignments.map((item) => item.themeId).join(",") === "theme_1,theme_2,theme_3", "ids stay put");

const art = themeText("art_style", "Art");
const dup = planThemeIds([
  { key: "src", origin: "restored", themeJson: art, enableJson: watchArt },
  { key: "copy", origin: "duplicate", themeJson: art, enableJson: watchArt },
]);
assert(dup.assignments[0].themeId === "art_style" && dup.assignments[0].changed === false && dup.assignments[0].themeJson === art, "source manual id kept");
assert(dup.assignments[1].themeId === "theme_1" && dup.assignments[1].changed === true, "duplicate manual id becomes theme_1");
assert(dup.assignments[0].enableJson === watchArt && dup.assignments[1].enableJson === watchArt, "duplicate enable stays");
assert(dup.conflicts.length === 0, "duplicate is not a restored conflict");

const character = themeText("character_pack", "Cast");
const restored = planThemeIds([
  { key: "art", origin: "restored", themeJson: art, enableJson: watchArt },
  { key: "cast", origin: "restored", themeJson: character, enableJson: emptyEnable },
]);
assert(restored.conflicts.length === 0, "unique restore");
assert(restored.assignments[0].themeJson === art && restored.assignments[1].themeJson === character, "restore text untouched");
assert(restored.assignments[0].enableJson === watchArt, "restore enable untouched");

const clash = planThemeIds([
  { key: "a", label: "Theme #4", origin: "restored", themeJson: art, enableJson: watchArt },
  { key: "b", label: "Theme #9", origin: "restored", themeJson: art, enableJson: watchArt },
]);
assert(clash.conflicts.length === 1, "one restored conflict");
assert(clash.conflicts[0].themeId === "art_style", "conflict names the id");
assert(clash.conflicts[0].keys.join(",") === "a,b", "conflict names the nodes");
assert(clash.conflicts[0].reason.includes("art_style") && clash.conflicts[0].reason.includes("Theme #4"), "conflict reason is specific");
assert(clash.assignments[0].themeJson === art && clash.assignments[1].themeJson === art, "conflict does not rewrite theme json");
assert(clash.assignments[0].enableJson === watchArt && clash.assignments[1].enableJson === watchArt, "conflict does not rewrite enable");
assert(clash.assignments.every((item) => item.changed === false), "conflict assignments unchanged");

const beside = planThemeIds([
  { key: "fresh", origin: "new", themeJson: themeText("theme_1"), enableJson: emptyEnable },
  { key: "old", origin: "restored", themeJson: themeText("theme_1"), enableJson: watchTheme1 },
]);
assert(beside.assignments.find((item) => item.key === "old").themeId === "theme_1", "restored theme_1 wins");
assert(beside.assignments.find((item) => item.key === "old").changed === false, "restored widget stays");
assert(beside.assignments.find((item) => item.key === "fresh").themeId === "theme_2", "new node takes the next id");
assert(beside.assignments.find((item) => item.key === "old").enableJson === watchTheme1, "restored enable stays");
assert(beside.conflicts.length === 0, "new beside restored is not a conflict");

const gap = planThemeIds([
  { key: "r1", origin: "restored", themeJson: themeText("theme_1"), enableJson: emptyEnable },
  { key: "r3", origin: "restored", themeJson: themeText("theme_3"), enableJson: emptyEnable },
  { key: "copy", origin: "duplicate", themeJson: themeText("theme_1"), enableJson: watchTheme1 },
]);
assert(gap.assignments.find((item) => item.key === "copy").themeId === "theme_2", "gap fill");
assert(gap.assignments.find((item) => item.key === "r1").changed === false, "theme_1 kept");
assert(gap.assignments.find((item) => item.key === "r3").changed === false, "theme_3 kept");

const blank = planThemeIds([
  { key: "kept", origin: "restored", themeJson: art, enableJson: watchArt },
  { key: "blank", origin: "restored", themeJson: themeText("   "), enableJson: emptyEnable },
]);
assert(blank.assignments[0].themeId === "art_style" && blank.assignments[0].changed === false, "manual restore kept");
assert(blank.assignments[1].themeId === "theme_1" && blank.assignments[1].changed === true, "blank restore filled");
assert(blank.conflicts.length === 0, "blank restore is unambiguous");

const unreadable = planThemeIds([{ key: "bad", origin: "new", themeJson: "{", enableJson: watchArt }]);
assert(unreadable.assignments[0].changed === false && unreadable.assignments[0].themeJson === "{", "bad json left");
assert(unreadable.assignments[0].enableJson === watchArt, "bad json enable left");
assert(unreadable.conflicts.length === 1 && unreadable.conflicts[0].reason.includes("bad"), "bad json reported");

const contested = planThemeIds([
  { key: "a", origin: "restored", themeJson: themeText("theme_1"), enableJson: watchTheme1 },
  { key: "b", origin: "restored", themeJson: themeText("theme_1"), enableJson: watchTheme1 },
  { key: "c", origin: "new", themeJson: themeText("theme_1"), enableJson: emptyEnable },
]);
assert(contested.assignments[0].changed === false && contested.assignments[1].changed === false, "contested pair stays");
assert(contested.assignments[2].themeId === "theme_2", "new node avoids the contested id");
assert(contested.conflicts.length === 1 && contested.conflicts[0].keys.join(",") === "a,b", "conflict is only the restored pair");
assert(contested.conflicts[0].reason.includes("left unchanged"), "conflict does not claim enable rules were retargeted");
assert(contested.conflicts[0].reason.includes("repeated theme_id"), "conflict names the decision chain");

const themeBody = {
  version: 1,
  theme_id: "art_style",
  title: "T",
  instructions: "I",
  select_mode: "single",
  options: [
    { option_id: "anime", label: "Anime", description: "" },
    { option_id: "none", label: "", description: "" },
  ],
};
assert(optionOutputName(themeBody.options[0]) === "Anime (anime)", "label and id");
assert(optionOutputName({ option_id: "none", label: "  " }) === "none", "id only");
const planned = planOptionOutputs(JSON.stringify(themeBody));
assert(planned.ok && planned.slots.length === MAX_OPTION_OUTPUTS, "32 slots");
assert(planned.slots[0].name === "Anime (anime)" && planned.slots[0].hidden === false, "first visible");
assert(planned.slots[0].label === "Anime" && planned.slots[0].localized_name === "Anime", "first visible label drops id");
assert(planned.slots[1].name === "none" && planned.slots[1].type === "S1_DECISION", "second visible");
assert(planned.slots[1].label === "Option 2" && planned.slots[1].localized_name === "Option 2", "empty none uses table display number");
assert(planned.slots[2].hidden === true && planned.slots[2].name === "", "pad hidden");
assert(planned.reportIndex === 32, "report index");

assert(optionDisplayText({ label: " bikini ", description: "ignored" }) === "bikini", "label wins over description");
assert(optionDisplayText({ label: "  ", description: " dress " }) === "dress", "description fills empty label");
assert(optionDisplayText({ label: "", description: "" }) === "", "both empty");

const displayTheme = {
  version: 1,
  theme_id: "outfit",
  title: "Outfit",
  instructions: "Choose.",
  select_mode: "single",
  none_option_id: "option_2",
  options: [
    { option_id: "option_1", label: "bikini", description: "" },
    { option_id: "option_2", label: "None", description: "" },
    { option_id: "option_3", label: "dress", description: "" },
  ],
};
assert(
  JSON.stringify(optionOutputLabels(displayTheme.options, "option_2")) === JSON.stringify(["bikini", "None", "dress"]),
  "labels are names only, in prompt order, None text kept",
);
const plannedDisplay = planOptionOutputs(JSON.stringify(displayTheme));
assert(plannedDisplay.ok, "display plan ok");
assert(plannedDisplay.slots[0].name === "bikini (option_1)" && plannedDisplay.slots[0].label === "bikini", "bikini name+label");
assert(plannedDisplay.slots[1].name === "None (option_2)" && plannedDisplay.slots[1].label === "None", "None name+label mid-id");
assert(plannedDisplay.slots[2].name === "dress (option_3)" && plannedDisplay.slots[2].label === "dress", "dress name+label");
assert(plannedDisplay.slots[0].localized_name === "bikini" && plannedDisplay.slots[2].localized_name === "dress", "localized_name matches");

const emptyTheme = {
  version: 1,
  theme_id: "empty_names",
  title: "Empty",
  instructions: "Choose.",
  select_mode: "single",
  none_option_id: "option_2",
  options: [
    { option_id: "option_1", label: "  ", description: "" },
    { option_id: "option_2", label: "", description: "" },
    { option_id: "option_3", label: "", description: "  " },
  ],
};
assert(
  JSON.stringify(optionOutputLabels(emptyTheme.options, "option_2")) === JSON.stringify(["Option 1", "Option 3", "Option 2"]),
  "empty names fall back to Option N with table display numbers, mapped to prompt order",
);
const plannedEmpty = planOptionOutputs(JSON.stringify(emptyTheme));
assert(plannedEmpty.slots[0].name === "option_1" && plannedEmpty.slots[0].label === "Option 1", "empty first keeps id as name");
assert(plannedEmpty.slots[1].name === "option_2" && plannedEmpty.slots[1].label === "Option 3", "empty mid-id None is table row 3");
assert(plannedEmpty.slots[2].name === "option_3" && plannedEmpty.slots[2].label === "Option 2", "empty third is table row 2");

const dupTheme = {
  version: 1,
  theme_id: "dups",
  title: "Dups",
  instructions: "Choose.",
  select_mode: "single",
  none_option_id: "option_2",
  options: [
    { option_id: "option_1", label: "bikini", description: "" },
    { option_id: "option_2", label: "None", description: "" },
    { option_id: "option_3", label: "bikini", description: "" },
  ],
};
assert(
  JSON.stringify(optionOutputLabels(dupTheme.options, "option_2")) === JSON.stringify(["bikini", "None", "bikini #2"]),
  "duplicate names: first stays bare, later uses table display number",
);
const plannedDup = planOptionOutputs(JSON.stringify(dupTheme));
assert(plannedDup.slots[0].name === "bikini (option_1)" && plannedDup.slots[0].label === "bikini", "dup first name unchanged");
assert(plannedDup.slots[2].name === "bikini (option_3)" && plannedDup.slots[2].label === "bikini #2", "dup later gets #2");
assert(plannedDup.slots[1].name === "None (option_2)" && plannedDup.slots[1].label === "None", "None not treated as a dup of bikini");
const invalidPlan = planOptionOutputs("{");
assert(!invalidPlan.ok && invalidPlan.slots === null, "invalid plan leaves slots null");

const fresh = {
  id: 3,
  outputs: [
    { name: "option_1", type: "S1_DECISION", links: [4] },
    { name: "report_json", type: "STRING", links: [5] },
  ],
  graph: {
    links: {
      4: { id: 4, origin_id: 3, origin_slot: 0, target_id: 1, target_slot: 0 },
      5: { id: 5, origin_id: 3, origin_slot: 1, target_id: 2, target_slot: 0 },
    },
  },
};
const firstSync = relinkOptionSlots(fresh, planned.slots);
assert(firstSync.first === true && firstSync.moved === 0, "first sync does not move");
assert(fresh.graph.links[4].origin_slot === 0, "first leaves the option link");
assert(fresh.outputs[0].name === "Anime (anime)" && fresh.outputs[0].label === "Anime", "relink keeps slot name, sets label");
assert(fresh.outputs[0].localized_name === "Anime", "relink sets localized_name");
assert(fresh.outputs[1].name === "none" && fresh.outputs[1].label === "Option 2", "empty none label is Option 2");
assert(fresh.graph.links[5].origin_slot === 1, "report name alone does not retarget");
assert(fresh.outputs[0].s1OptionId === "anime", "stamped by index");

const reorderBody = {
  ...themeBody,
  options: [
    { option_id: "none", label: "None", description: "" },
    { option_id: "anime", label: "Anime", description: "" },
  ],
};
const reordered = planOptionOutputs(JSON.stringify(reorderBody));
const wired = {
  id: 7,
  outputs: [
    { name: "Anime (anime)", type: "S1_DECISION", links: [1], s1OptionId: "anime" },
    { name: "none", type: "S1_DECISION", links: [2], s1OptionId: "none" },
  ],
  graph: {
    links: {
      1: { id: 1, origin_id: 7, origin_slot: 0, target_id: 8, target_slot: 0, type: "S1_DECISION" },
      2: { id: 2, origin_id: 7, origin_slot: 1, target_id: 9, target_slot: 0, type: "S1_DECISION" },
    },
    _nodes: [],
  },
};
const moved = relinkOptionSlots(wired, reordered.slots);
assert(moved.first === false && moved.moved === 2, "later sync moves both");
assert(wired.graph.links[1].origin_slot === 1, "anime follows its id");
assert(wired.graph.links[2].origin_slot === 0, "none follows its id");
assert(wired.outputs[0].links.includes(2) && wired.outputs[1].links.includes(1), "link ids follow the slots");

const dropped = {
  id: 1,
  outputs: [
    { name: "Gone", type: "S1_DECISION", links: [9], s1OptionId: "gone" },
    { name: "Anime (anime)", type: "S1_DECISION", links: [], s1OptionId: "anime" },
  ],
  graph: {
    links: {
      9: { id: 9, origin_id: 1, origin_slot: 0, target_id: 2, target_slot: 3, type: "S1_DECISION" },
    },
    _nodes: [{ id: 2, inputs: [{}, {}, {}, { link: 9 }] }],
  },
};
const drop = relinkOptionSlots(dropped, planned.slots);
assert(drop.dropped === 0 && drop.kept === 1, "a connected missing option is kept");
assert(dropped.graph.links[9].origin_slot === 0, "gone option wire stays on its slot");
assert(dropped.graph._nodes[0].inputs[3].link === 9, "target input stays connected");

const sibling = {
  id: 11,
  outputs: [
    { name: "Anime (anime)", type: "S1_DECISION", links: [21], s1OptionId: "anime" },
    { name: "none", type: "S1_DECISION", links: [], s1OptionId: "none" },
  ],
  graph: {
    links: {
      21: { id: 21, origin_id: 11, origin_slot: 0, target_id: 12, target_slot: 0, type: "S1_DECISION" },
    },
  },
};
const siblingSync = relinkOptionSlots(sibling, planned.slots);
assert(siblingSync.dropped === 0, "an unused sibling pad does not drop a live option wire");
assert(sibling.graph.links[21].origin_slot === 0, "selected slot stays linked");
assert(sibling.outputs[0].hidden === false && sibling.outputs[0].links.includes(21), "live option stays visible");
assert(sibling.outputs[2].hidden === true && sibling.outputs[2].name === "·", "unused unconnected pad is marked hidden before compact");
assert(sibling.graph.links[21].origin_slot === 0 && sibling.outputs[0].links.includes(21), "marking a pad hidden does not drop a live option wire");
const siblingCompact = compactOptionOutputs(sibling);
assert(siblingCompact.ok && sibling.outputs.length === 3, "compact drops unused pads and keeps report");
assert(sibling.outputs[0].s1OptionId === "anime" && sibling.outputs[0].hidden === false, "live option remains first");
assert(sibling.outputs[1].s1OptionId === "none", "none option stays");
assert(sibling.outputs[2].name === "report_json" && sibling.outputs[2].s1PromptIndex === 32, "report stays last with prompt index 32");
assert(sibling.graph.links[21].origin_slot === 0 && sibling.outputs[0].links.includes(21), "compact does not drop a live option wire");
const siblingExpand = expandOptionOutputs(sibling);
assert(siblingExpand.ok && sibling.outputs.length === 33, "expand restores 32 options plus report");
assert(sibling.outputs[32].name === "report_json" && sibling.outputs[32].s1PromptIndex === 32, "report returns to index 32");
assert(sibling.graph.links[21].origin_slot === 0, "expand puts the live option wire back on slot 0");

const livePad = {
  id: 13,
  outputs: Array.from({ length: 33 }, (_, index) => ({
    name: index === 32 ? "report_json" : `option_${index + 1}`,
    type: index === 32 ? "STRING" : "S1_DECISION",
    links: index === 5 ? [22] : [],
    s1OptionId: index === 0 ? "anime" : index === 1 ? "none" : "",
  })),
  graph: {
    links: {
      22: { id: 22, origin_id: 13, origin_slot: 5, target_id: 14, target_slot: 1, type: "S1_DECISION" },
    },
  },
};
relinkOptionSlots(livePad, planned.slots);
assert(livePad.outputs[5].hidden === false, "a pad with a live wire is not hidden");
assert(livePad.graph.links[22].origin_slot === 5, "live pad wire is kept");
assert(livePad.outputs[5].links.includes(22), "live pad link id stays on the output");
assert(livePad.outputs[5].name === "option_6", "a linked pad name is not blanked");
compactOptionOutputs(livePad);
const liveKept = livePad.outputs.find((output) => output.s1PromptIndex === 5);
assert(liveKept && liveKept.hidden === false, "a live unused-planned pad is kept when compacting");
assert(livePad.graph.links[22].origin_slot === livePad.outputs.indexOf(liveKept), "live pad wire follows the compacted index");
assert(liveKept.links.includes(22), "live pad link id stays on the output after compact");
expandOptionOutputs(livePad);
assert(livePad.outputs[5].s1PromptIndex === 5, "expand puts the live pad back at prompt index 5");
assert(livePad.graph.links[22].origin_slot === 5, "expand restores the live pad wire to slot 5");

// Frontend 1.57: graph.links is a Map, ids may be strings, and the slot's
// output.links mirror can be null. CamelCase originId/originSlot counts.
const linksOnly = {
  id: "15",
  outputs: [
    { name: "option_1", type: "S1_DECISION", links: null },
  ],
  graph: {
    links: new Map([
      [30, { id: 30, originId: 15, originSlot: 0, targetId: 16, targetSlot: 0, type: "S1_DECISION" }],
    ]),
  },
};
const linksOnlySync = relinkOptionSlots(linksOnly, planned.slots);
assert(linksOnlySync.first === true && linksOnlySync.dropped === 0 && linksOnlySync.moved === 0, "map-only first sync stamps");
assert(linksOnly.outputs[0].hidden === false && linksOnly.outputs[0].s1OptionId === "anime", "map wire keeps the socket");
assert(linksOnly.outputs[0].links === null, "first sync does not rewrite a null links mirror");
assert(linksOnly.graph.links.get(30).originSlot === 0, "map link stays on the option");
assert(linksOnly.outputs[2].hidden === true && linksOnly.outputs[2].name === "·", "unlinked pad is marked hidden before compact");
compactOptionOutputs(linksOnly);
assert(linksOnly.outputs.some((output) => output.name === "report_json" && output.s1PromptIndex === 32), "compact keeps report_json");
assert(!linksOnly.outputs.some((output, index) => index < linksOnly.outputs.length - 1 && output.hidden), "compacted option sockets are visible");
assert(linksOnly.graph.links.get(30).originSlot === 0, "map link stays on the option after compact");

class StoreOutput {
  constructor(name, optionId, ids) {
    this.name = name;
    this.type = "S1_DECISION";
    this.s1OptionId = optionId;
    this._ids = ids;
  }
  get links() { return this._ids; }
  set links(_value) { throw new Error("output.links assignment drops the wire on frontend 1.57"); }
}
const storeNode = {
  id: 40,
  outputs: [
    new StoreOutput("Anime (anime)", "anime", [71]),
    new StoreOutput("none", "none", [72]),
  ],
  graph: {
    links: new Map([
      [71, { id: 71, origin_id: 40, origin_slot: 0, target_id: 41, target_slot: 0, type: "S1_DECISION" }],
      [72, { id: 72, originId: "40", originSlot: 1, targetId: 42, targetSlot: 0, type: "S1_DECISION" }],
    ]),
  },
};
const storeMoved = relinkOptionSlots(storeNode, reordered.slots);
assert(storeMoved.dropped === 0 && storeMoved.moved === 2, "reorder retargets store-backed links");
assert(storeNode.graph.links.get(71).origin_slot === 1, "anime follows its id without assigning links");
assert(storeNode.graph.links.get(72).originSlot === 0, "camelCase none follows its id");
assert(storeNode.outputs[0].hidden === false && storeNode.outputs[1].hidden === false, "retargeted sockets stay visible");

// A later sync must not drop a wire whose slot was never stamped, and must
// not drop that wire just because the planned slot is an unused pad.
const unstampedPad = {
  id: 21,
  outputs: [
    { name: "Anime (anime)", type: "S1_DECISION", links: [], s1OptionId: "anime" },
  ],
  graph: {
    links: {
      40: { id: 40, origin_id: "21", origin_slot: 4, target_id: 22, target_slot: 1, type: "S1_DECISION" },
    },
  },
};
const unstamped = relinkOptionSlots(unstampedPad, planned.slots);
assert(unstamped.dropped === 0 && unstamped.kept === 0, "empty s1OptionId is not a drop");
assert(unstampedPad.graph.links[40].origin_slot === 4, "unstamped pad wire stays");
assert(unstampedPad.outputs[4].hidden === false, "linked unused-planned slot is not hidden");
assert(unstampedPad.outputs[4].s1OptionId === "", "pad stamp does not invent an option id");

const prompts = {
  inputs: [
    { name: "positive", link: 1 },
    { name: "settings", link: 2 },
    { name: "negative", link: 3 },
  ],
  graph: {
    links: {
      1: { id: 1, target_slot: 0 },
      2: { id: 2, target_slot: 1 },
      3: { id: 3, target_slot: 2 },
    },
  },
};
const ordered = orderThemePromptInputs(prompts);
assert(ordered.moved === true, "optional negative is moved under positive");
assert(prompts.inputs.map((item) => item.name).join(",") === "positive,negative,settings", "prompt order");
assert(prompts.graph.links[1].target_slot === 0, "positive link stays");
assert(prompts.graph.links[3].target_slot === 1, "negative link follows the socket");
assert(prompts.graph.links[2].target_slot === 2, "settings link remapped");
const againOrder = orderThemePromptInputs(prompts);
assert(againOrder.moved === false, "second prompt order pass is a no-op");

const reused = ensureDefaultNoneOption({
  options: [
    { option_id: "option_1", label: "bikini", description: "bikini", tags: ["bikini"] },
    { option_id: "option_2", label: "None", description: "Not on the list" },
  ],
});
assert(reused.reused === true && reused.added === false, "user None option is reused");
assert(reused.model.none_option_id === "option_2", "none_option_id points at existing None");
assert(reused.model.options.length === 2, "reused none does not add a slot");

const added = ensureDefaultNoneOption({
  options: [{ option_id: "option_1", label: "bikini", description: "bikini", tags: ["bikini"] }],
});
assert(added.added === true && added.model.options.length === 2, "default none is appended");
assert(added.model.options[0].option_id === "option_1", "append keeps the first slot");
assert(added.model.none_option_id === "none" && added.model.options[1].label === DEFAULT_NONE_LABEL, "appended default None");
assert(DEFAULT_NONE_LABEL === "None", "new defaults are English None");
assert(isNoneLikeOption({ label: "None", description: "Not on the list" }), "None / Not on the list is none-like");

const collectNode = {
  id: 90,
  inputs: [
    { name: "a", type: "S1_DECISION", link: 1 },
    { name: "b", type: "S1_DECISION", link: 2 },
  ],
  graph: {
    links: {
      1: { id: 1, origin_id: 1, origin_slot: 0, target_id: 90, target_slot: 0 },
      2: { id: 2, origin_id: 1, origin_slot: 1, target_id: 90, target_slot: 1 },
    },
  },
};
const collectSync = syncCollectInputs(collectNode);
assert(collectSync.ok, "collect sync ok");
assert(collectNode.inputs[0].name === "a" && collectNode.inputs[0].hidden === false, "a stays visible");
assert(collectNode.inputs[1].name === "b" && collectNode.inputs[1].hidden === false, "b stays visible");
assert(collectNode.inputs[2].name === "c" && collectNode.inputs[2].hidden === false, "empty c appears");
assert(collectNode.inputs.length === 3, "later collect pads are not kept on the node");
assert(collectNode.graph.links[1].target_slot === 0 && collectNode.graph.links[2].target_slot === 1, "collect wires stay");

const tags = collectGraphTags({
  _nodes: [
    { type: "S1LoraLibrary", widgets: [{ name: "library_json", value: JSON.stringify({ loras: [{ tags: ["bikini", "style"] }] }) }] },
    { type: "S1ThemeRoot", widgets: [{ name: "theme_json", value: JSON.stringify({ options: [{ tags: ["bikini", "other"] }] }) }] },
  ],
});
assert(tags.join(",") === "bikini,style,other", "graph tags are unique and ordered");

// Theme display order: None last even when option_2 sits in the middle.
const midNoneModel = {
  none_option_id: "option_2",
  options: [
    { option_id: "option_1", label: "bikini", description: "bikini", tags: ["bikini"] },
    { option_id: "option_2", label: "None", description: "以上皆非", tags: [] },
    { option_id: "option_3", label: "foo", description: "foo", tags: ["style"] },
  ],
};
const displayed = optionDisplayOrder(midNoneModel.options, midNoneModel.none_option_id);
assert(displayed.map((option) => option.option_id).join(",") === "option_1,option_3,option_2", "None is last in display order");
assert(midNoneModel.options[1].option_id === "option_2", "display order does not rewrite the array");

const grown = addThemeOption(JSON.parse(JSON.stringify(midNoneModel)));
assert(grown.ok && grown.option.option_id === "option_4", "new option gets the next free id");
assert(grown.model.none_option_id === "option_2" && grown.model.options[1].option_id === "option_2", "adding keeps None id and index");
assert(grown.model.options[3].option_id === "option_4", "new option is appended after existing slots");
assert(optionDisplayOrder(grown.model.options, grown.model.none_option_id).map((option) => option.option_id).join(",") === "option_1,option_3,option_4,option_2", "new option appears before None");

const refused = deleteThemeOption(JSON.parse(JSON.stringify(midNoneModel)), "option_2");
assert(!refused.ok, "None cannot be deleted");
const deleted = deleteThemeOption(JSON.parse(JSON.stringify(midNoneModel)), "option_1");
assert(deleted.ok && deleted.model.options.map((option) => option.option_id).join(",") === "option_2,option_3", "deleting a user option keeps None id");
const unmoved = moveThemeOption(JSON.parse(JSON.stringify(midNoneModel)), "option_2", -1);
assert(!unmoved.ok || unmoved.moved === false, "None cannot be moved");
const shifted = moveThemeOption(JSON.parse(JSON.stringify(midNoneModel)), "option_3", -1);
assert(shifted.ok && shifted.moved && shifted.model.options.map((option) => option.option_id).join(",") === "option_3,option_2,option_1", "move swaps non-None slots and leaves None in place");

const midNode = {
  id: 21,
  widgets: [{ name: "theme_json", value: JSON.stringify(midNoneModel) }],
  outputs: [
    { name: "bikini (option_1)", type: "S1_DECISION", links: [41], s1OptionId: "option_1" },
    { name: "None (option_2)", type: "S1_DECISION", links: [42], s1OptionId: "option_2" },
    { name: "foo (option_3)", type: "S1_DECISION", links: [43], s1OptionId: "option_3" },
  ],
  graph: {
    links: {
      41: { id: 41, origin_id: 21, origin_slot: 0, target_id: 22, target_slot: 0, type: "S1_DECISION" },
      42: { id: 42, origin_id: 21, origin_slot: 1, target_id: 22, target_slot: 1, type: "S1_DECISION" },
      43: { id: 43, origin_id: 21, origin_slot: 2, target_id: 22, target_slot: 2, type: "S1_DECISION" },
    },
  },
};
compactOptionOutputs(midNode, "option_2");
assert(midNode.outputs.map((output) => output.s1OptionId || output.name).join(",") === "option_1,option_3,option_2,report_json", "compact shows None last among option sockets");
assert(midNode.outputs[2].s1PromptIndex === 1 && midNode.graph.links[42].origin_slot === 2, "None keeps prompt index 1 and remaps the visual slot");
assert(midNode.graph.links[41].origin_slot === 0 && midNode.graph.links[43].origin_slot === 1, "other option wires follow display order");
expandOptionOutputs(midNode);
assert(midNode.outputs.length === 33 && midNode.outputs[1].s1OptionId === "option_2", "expand restores None to prompt index 1");
assert(midNode.graph.links[42].origin_slot === 1 && midNode.graph.links[43].origin_slot === 2, "expand restores backend origin slots");
compactOptionOutputs(midNode, "option_2");
assert(midNode.outputs[2].s1OptionId === "option_2" && midNode.graph.links[42].origin_slot === 2, "serialize/prompt roundtrip can compact again");

// Legacy auto-generated None label is relabeled only on the designated None option.
const legacyNone = {
  version: 1,
  theme_id: "theme_1",
  none_option_id: "option_2",
  options: [
    { option_id: "option_1", label: LEGACY_DEFAULT_NONE_TEXT, description: "user option", tags: ["keep"] },
    { option_id: "option_2", label: LEGACY_DEFAULT_NONE_TEXT, description: LEGACY_DEFAULT_NONE_TEXT, tags: [LEGACY_DEFAULT_NONE_TEXT] },
  ],
};
const ensuredLegacy = ensureDefaultNoneOption(JSON.parse(JSON.stringify(legacyNone)));
assert(ensuredLegacy.changed === true && ensuredLegacy.model.options[1].label === "None", "auto-generated None label is relabeled");
assert(ensuredLegacy.model.options[1].description === "None", "auto-generated None description is relabeled");
assert(ensuredLegacy.model.options[1].tags[0] === LEGACY_DEFAULT_NONE_TEXT, "None tags are not rewritten");
assert(ensuredLegacy.model.options[0].label === LEGACY_DEFAULT_NONE_TEXT, "user option text is left alone");
assert(legacyNone.options[1].label === LEGACY_DEFAULT_NONE_TEXT, "ensure does not mutate the caller's copy in this test fixture path");
const customNone = ensureDefaultNoneOption({
  none_option_id: "option_2",
  options: [
    { option_id: "option_1", label: "bikini" },
    { option_id: "option_2", label: LEGACY_DEFAULT_NONE_TEXT, description: "Not on the list", tags: [] },
  ],
});
assert(customNone.model.options[1].label === "None" && customNone.model.options[1].description === "Not on the list", "only the exact default field is rewritten");
assert(!relabelLegacyDefaultNoneOption({ label: "None of these", description: "custom" }), "user-typed None text is not relabeled");

const labelModel = {
  version: 1,
  theme_id: "outfit",
  title: "Outfit",
  instructions: "Choose.",
  select_mode: "single",
  none_option_id: "option_2",
  options: [
    { option_id: "option_1", label: "bikini", description: "" },
    { option_id: "option_2", label: "None", description: "" },
    { option_id: "option_3", label: "dress", description: "" },
  ],
};
const labelPlan = planOptionOutputs(JSON.stringify(labelModel));
const labelNode = {
  id: 31,
  widgets: [{ name: "theme_json", value: JSON.stringify(labelModel) }],
  outputs: [
    { name: "bikini (option_1)", type: "S1_DECISION", links: [51], s1OptionId: "option_1", s1PromptIndex: 0 },
    { name: "None (option_2)", type: "S1_DECISION", links: [52], s1OptionId: "option_2", s1PromptIndex: 1 },
    { name: "dress (option_3)", type: "S1_DECISION", links: [53], s1OptionId: "option_3", s1PromptIndex: 2 },
    { name: "report_json", type: "STRING", links: [54] },
  ],
  graph: {
    links: {
      51: { id: 51, origin_id: 31, origin_slot: 0, target_id: 32, target_slot: 0, type: "S1_DECISION" },
      52: { id: 52, origin_id: 31, origin_slot: 1, target_id: 32, target_slot: 1, type: "S1_DECISION" },
      53: { id: 53, origin_id: 31, origin_slot: 2, target_id: 32, target_slot: 2, type: "S1_DECISION" },
      54: { id: 54, origin_id: 31, origin_slot: 3, target_id: 33, target_slot: 0, type: "STRING" },
    },
  },
};
expandOptionOutputs(labelNode);
relinkOptionSlots(labelNode, labelPlan.slots);
assert(labelNode.outputs[0].name === "bikini (option_1)" && labelNode.outputs[0].label === "bikini", "relink name unchanged");
assert(labelNode.outputs[1].name === "None (option_2)" && labelNode.outputs[1].label === "None", "None label has no option_id");
assert(labelNode.outputs[2].name === "dress (option_3)" && labelNode.outputs[2].localized_name === "dress", "dress localized_name");
assert(labelNode.outputs[0].s1OptionId === "option_1" && labelNode.outputs[0].s1PromptIndex === 0, "prompt index 0 kept");
assert(labelNode.outputs[1].s1OptionId === "option_2" && labelNode.outputs[1].s1PromptIndex === 1, "mid-id None keeps prompt index 1");
assert(labelNode.graph.links[51].origin_slot === 0 && labelNode.graph.links[52].origin_slot === 1 && labelNode.graph.links[53].origin_slot === 2, "links stay on prompt indexes after relink");
compactOptionOutputs(labelNode, "option_2");
assert(labelNode.outputs.map((output) => output.label || output.name).join(",") === "bikini,dress,None,report_json", "compact visible labels are names only, None last");
assert(labelNode.outputs[0].name === "bikini (option_1)" && labelNode.outputs[2].name === "None (option_2)", "compact leaves internal slot names");
assert(labelNode.graph.links[52].origin_slot === 2 && labelNode.graph.links[53].origin_slot === 1, "compact remaps visual origins only");
expandOptionOutputs(labelNode);
assert(labelNode.outputs[0].label === "bikini" && labelNode.outputs[1].label === "None" && labelNode.outputs[2].label === "dress", "expand keeps labels");
assert(labelNode.outputs[0].name === "bikini (option_1)" && labelNode.outputs[1].s1PromptIndex === 1, "expand restores names and prompt index");
assert(labelNode.graph.links[52].origin_slot === 1 && labelNode.graph.links[53].origin_slot === 2, "expand restores link slots");
const snapshot = labelNode.outputs.map((output) => ({
  name: output?.name,
  type: output?.type,
  links: output?.links,
  localized_name: output?.localized_name,
  label: output?.label,
  s1OptionId: output?.s1OptionId,
  s1PromptIndex: output?.s1PromptIndex,
}));
assert(snapshot[0].name === "bikini (option_1)" && snapshot[0].label === "bikini" && snapshot[0].localized_name === "bikini", "serialize snapshot has name+label");
assert(snapshot[1].s1OptionId === "option_2" && snapshot[1].s1PromptIndex === 1 && snapshot[1].links[0] === 52, "serialize keeps id, index, links");
compactOptionOutputs(labelNode, "option_2");
assert(labelNode.outputs[2].s1OptionId === "option_2" && labelNode.outputs[2].label === "None", "roundtrip compact still labeled None");

// Node size policy: grow/shrink with content, preserve user width, keep user height floor.
const grew = nextEditorNodeSize({ currentWidth: 420, currentHeight: 120, minWidth: 420, minHeight: 80, contentHeight: 200 });
assert(grew.width === 420 && grew.height === 200, "height grows with content");
const shrunk = nextEditorNodeSize({ currentWidth: 420, currentHeight: 200, minWidth: 420, minHeight: 80, contentHeight: 100 });
assert(shrunk.width === 420 && shrunk.height === 100, "height shrinks when chips/content shrink");
const wide = nextEditorNodeSize({ currentWidth: 640, currentHeight: 200, minWidth: 420, minHeight: 80, contentHeight: 100, userMinWidth: 640 });
assert(wide.width === 640 && wide.height === 100, "manually enlarged width is preserved while height can shrink");
const tall = nextEditorNodeSize({ currentWidth: 420, currentHeight: 400, minWidth: 420, minHeight: 80, contentHeight: 100, userMinHeight: 400 });
assert(tall.width === 420 && tall.height === 400, "does not shrink below a user-set height");
const growPastUser = nextEditorNodeSize({ currentWidth: 420, currentHeight: 400, minWidth: 420, minHeight: 80, contentHeight: 500, userMinHeight: 400 });
assert(growPastUser.height === 500, "content can still grow past a user-set height");
assert(measureHostHeight(null, 80) === 80, "measure falls back when no host");
assert(measureHostHeight({ scrollHeight: 24, offsetHeight: 20, getBoundingClientRect: () => ({ height: 22 }) }, 0) === 24, "measure uses the largest host height");

const sized = { size: [420, 120], setSize(next) { this.size = next; this.sets = (this.sets || 0) + 1; } };
installEditorSizeGuard(sized);
applyEditorNodeSize(sized, { minWidth: 420, minHeight: 80, contentHeight: 220 });
assert(sized.size[0] === 420 && sized.size[1] === 220, "apply grows the node to content");
applyEditorNodeSize(sized, { minWidth: 420, minHeight: 80, contentHeight: 140 });
assert(sized.size[1] === 140, "apply shrinks back when content shrinks");
sized.onResize([640, 360]);
assert(sized.__s1UserMinWidth === 640 && sized.__s1UserMinHeight === 360, "user resize is recorded");
applyEditorNodeSize(sized, { minWidth: 420, minHeight: 80, contentHeight: 140 });
assert(sized.size[0] === 640 && sized.size[1] === 360, "later auto size keeps the user width and height floor");
sized.__s1AutoSizing = true;
sized.onResize([640, 200]);
sized.__s1AutoSizing = false;
assert(sized.__s1UserMinHeight === 360, "auto setSize does not overwrite the user height floor");

// Row context menu: stop native Vue/canvas menu only on rows, never on left-click.
function fakeEvent(type, button, extra) {
  return {
    type,
    button,
    prevented: false,
    stopped: false,
    immediate: false,
    preventDefault() { this.prevented = true; },
    stopPropagation() { this.stopped = true; },
    stopImmediatePropagation() { this.immediate = true; },
    ...(extra || {}),
  };
}
function fakeEl() {
  const listeners = [];
  return {
    listeners,
    addEventListener(type, fn, opts) { listeners.push({ type, fn, capture: Boolean(opts === true || (opts && opts.capture)) }); },
    removeEventListener(type, fn) { const i = listeners.findIndex((item) => item.type === type && item.fn === fn); if (i >= 0) listeners.splice(i, 1); },
    dispatch(type, event) {
      for (const item of listeners.filter((entry) => entry.type === type && entry.capture)) item.fn(event);
      for (const item of listeners.filter((entry) => entry.type === type && !entry.capture)) item.fn(event);
    },
    getBoundingClientRect() { return this.box || { left: 0, top: 0, right: 0, bottom: 0 }; },
  };
}
const ev = fakeEvent("contextmenu", 2);
stopRowContextMenuEvent(ev);
assert(ev.prevented && ev.stopped && ev.immediate, "row contextmenu is fully stopped");
assert(isRightClickEvent(fakeEvent("pointerdown", 2)) && !isRightClickEvent(fakeEvent("pointerdown", 0)), "only button 2 counts as right-click");
const row = fakeEl();
let opened = 0;
bindRowContextMenu(row, () => { opened += 1; });
const ctx = fakeEvent("contextmenu", 2);
row.dispatch("contextmenu", ctx);
assert(opened === 1 && ctx.prevented && ctx.stopped && ctx.immediate, "capture contextmenu opens only the custom menu");
const left = fakeEvent("pointerdown", 0);
row.dispatch("pointerdown", left);
assert(opened === 1 && !left.prevented && !left.stopped, "left-click is not stopped");
const rightDown = fakeEvent("pointerdown", 2);
row.dispatch("pointerdown", rightDown);
assert(rightDown.stopped && rightDown.immediate && !rightDown.prevented, "right pointerdown stops bubble without preventDefault");

const menuNode = { __s1RowMenuEls: [], getExtraMenuOptions() { return ["native"]; } };
const hit = fakeEl();
hit.box = { left: 10, top: 10, right: 80, bottom: 40 };
registerRowMenuElement(menuNode, hit);
assert(hitTestNodeRows(menuNode, { clientX: 20, clientY: 20 }), "hit-test finds a row");
assert(!hitTestNodeRows(menuNode, { clientX: 200, clientY: 200 }), "hit-test misses elsewhere on the node");
assert(shouldSuppressNativeNodeMenu(menuNode, { clientX: 20, clientY: 20 }), "native menu suppressed on a row");
assert(!shouldSuppressNativeNodeMenu(menuNode, { clientX: 200, clientY: 200 }), "native menu kept off-row");
installNativeNodeMenuSuppress(menuNode);
assert(JSON.stringify(menuNode.getExtraMenuOptions({}, [], { clientX: 20, clientY: 20 })) === "[]", "getExtraMenuOptions is empty on a row hit");
assert(JSON.stringify(menuNode.getExtraMenuOptions({}, [], { clientX: 200, clientY: 200 })) === JSON.stringify(["native"]), "getExtraMenuOptions unchanged off-row");
clearRowMenuElements(menuNode);
assert(!shouldSuppressNativeNodeMenu(menuNode, { clientX: 20, clientY: 20 }), "cleared rows no longer suppress");

assert(JSON.stringify(tokenizeTags("bikini, Bikini, style, , style")) === JSON.stringify(["bikini", "style"]), "tags trim and dedupe case-insensitively");
assert(JSON.stringify(tokenizeTags(["foo", "bar", "foo"])) === JSON.stringify(["foo", "bar"]), "tag arrays dedupe");
assert(JSON.stringify(addTagToken(["bikini"], " Bikini ")) === JSON.stringify(["bikini"]), "adding a duplicate is a no-op");
assert(JSON.stringify(addTagToken(["bikini"], "style")) === JSON.stringify(["bikini", "style"]), "adding a new tag appends");
assert(JSON.stringify(removeTagToken(["bikini", "style"], 1)) === JSON.stringify(["bikini"]), "removeTagToken drops by index");
assert(tagsToCommaString(["bikini", "style"]) === "bikini, style", "tags serialize to a comma string");
assert(JSON.stringify(tokenizeTags(tagsToCommaString(["a", "b"]))) === JSON.stringify(["a", "b"]), "comma string roundtrips");
assert(parseTagToken("age:-2").name === "age" && parseTagToken("age:-2").weight === -2, "parse age:-2");
assert(parseTagToken("age:+1.5").weight === 1.5 && parseTagToken("age:+1.5").canonical === "age:1.5", "plus is optional and dropped in canonical form");
assert(parseTagToken("age:0").weight === 0, "parse age:0");
assert(parseTagToken("foo:bar").name === "foo:bar" && parseTagToken("foo:bar").weight == null, "non-numeric suffix stays in the name");
assert(parseTagToken("age:±2").weight == null, "plus-minus is not a weight");
assert(formatTagToken("age", -2) === "age:-2", "format negative weight");
assert(formatTagChipLabel("age:-2") === "age \u22122", "weighted chip uses a proper minus");
assert(formatTagChipLabel("age:1.5") === "age 1.5", "positive chip has no plus");
assert(JSON.stringify(tokenizeTags("age, age:-2")) === JSON.stringify(["age:-2"]), "later weight updates the same name");
assert(JSON.stringify(tokenizeTags("age:-2, age")) === JSON.stringify(["age"]), "later bare name drops the weight");
assert(JSON.stringify(tokenizeTags("Age:-2, age:+1.5")) === JSON.stringify(["Age:1.5"]), "first spelling, last weight");
assert(JSON.stringify(normalizeLibraryTags("age:-2, Style")) === JSON.stringify(["age", "Style"]), "library tags stay plain names");
assert(clampLoraStrength(6, true) === 5 && clampLoraStrength(-6, true) === -5, "slider strength clamps to -5..5");
assert(clampLoraStrength(6, false) === 6, "non-slider strength keeps the existing unbounded range");
const sliderLib = commitModel("lora", { loras: [{ name: "age.safetensors", strength: -2, tags: ["age:-2"], slider: true, enabled_default: true }] });
assert(sliderLib.ok, "slider library commits");
assert(sliderLib.model.loras[0].slider === true, "slider flag is stored");
assert(sliderLib.model.loras[0].strength_model === -2 && sliderLib.model.loras[0].strength_clip === -2, "slider can store a negative strength");
assert(JSON.stringify(sliderLib.model.loras[0].tags) === JSON.stringify(["age"]), "committed library tags drop weights");
const parsedLib = parseEditorDocument("lora", sliderLib.json);
assert(parsedLib.ok && parsedLib.model.loras[0].slider === true, "slider flag round-trips through JSON");
const legacyLib = parseEditorDocument("lora", '{ "loras": [{ "lora_id": "lora_1", "name": "x.safetensors", "strength_model": 0.8, "strength_clip": 0.8, "tags": ["age"] }] }');
assert(legacyLib.ok && legacyLib.model.loras[0].slider === false, "legacy library JSON defaults slider to off");
const themeTags = commitModel("theme", { theme_id: "t", title: "T", instructions: "I", select_mode: "single", options: [{ option_id: "o", label: "O", description: "D", tags: ["age:-2", "plain"] }] });
assert(themeTags.ok && JSON.stringify(themeTags.model.options[0].tags) === JSON.stringify(["age:-2", "plain"]), "option tags store age:-2 strings");
const graphTags = collectGraphTags({
  _nodes: [
    { comfyClass: "S1Theme", widgets: [{ name: "theme_json", value: themeTags.json }] },
  ],
}, null);
assert(JSON.stringify(graphTags) === JSON.stringify(["age", "plain"]), "autocomplete suggestions use the name part");

const tree = buildLoraMenuTree([
  "root.safetensors",
  "Anima/anima-turbo-lora-v0.2.safetensors",
  "Anima/sub/nested.safetensors",
  "Other/foo.safetensors",
]);
assert(tree.files.includes("root.safetensors"), "root files stay at the top level");
assert(tree.folders.has("Anima") && tree.folders.get("Anima").files.some((name) => name.includes("anima-turbo")), "Anima folder holds its file");
assert(tree.folders.get("Anima").folders.has("sub"), "nested folders are preserved");
const menu = loraChooserMenuItems(["Anima/a.safetensors", "b.safetensors"]);
assert(menu.some((item) => item.has_submenu && item.content.includes("Anima")), "menu nests folders as submenus");
assert(menu.some((item) => item.s1LoraName === "b.safetensors"), "root files are leaves with the full path");
const leaf = menu.find((item) => item.has_submenu).submenu.options[0];
assert(leaf.s1LoraName === "Anima/a.safetensors", "folder leaves keep the full LoRA path");

const start = [];
const cancelled = applyLoraChooserAction(start, "add", "", 0);
assert(!cancelled.changed && cancelled.loras.length === 0, "cancel / empty pick adds no row");
assert(!applyLoraChooserAction(start, "add", "None").changed, "picking None adds no row");
assert(!applyLoraChooserAction(start, "add", { content: "📁 Anima", has_submenu: true }).changed, "picking a folder adds no row");
const picked = applyLoraChooserAction(start, "add", "Anima/anima-turbo-lora-v0.2.safetensors");
assert(picked.changed && picked.loras.length === 1, "a pick adds one row");
assert(picked.row.enabled_default === true && picked.row.strength_model === 1 && picked.row.strength_clip === 1, "new row defaults are on and 1.00");
assert(picked.row.name === "Anima/anima-turbo-lora-v0.2.safetensors", "new row stores the full path");
const swapped = applyLoraChooserAction(picked.loras, "swap", "Other/foo.safetensors", 0);
assert(swapped.changed && swapped.loras[0].name === "Other/foo.safetensors", "swap changes only the name");
assert(swapped.loras[0].strength_model === 1 && swapped.loras.length === 1, "swap does not add a row or reset extras");
assert(!isUsableLoraName("None") && newLoraRowFromPick("None") === null, "None is not a usable LoRA pick");

assert(normalizeLoraPath("Anima\\sub\\nested.safetensors") === "Anima/sub/nested.safetensors", "backslash paths normalize to slashes");
assert(loraNameFromMenuValue("Anima\\xxx.safetensors") === "Anima/xxx.safetensors", "menu string values normalize separators");
assert(loraNameFromMenuValue({ s1LoraName: "Anima\\xxx.safetensors", content: "xxx.safetensors" }) === "Anima/xxx.safetensors", "menu object values normalize separators");

const nestedNames = [
  "root.safetensors",
  "Anima/anima-turbo-lora-v0.2.safetensors",
  "Anima/sub/nested.safetensors",
];
const rawMenu = loraChooserMenuItems(nestedNames);
const anima = rawMenu.find((item) => item.has_submenu && String(item.content).includes("Anima"));
assert(anima && anima.submenu && anima.submenu.callback === undefined, "raw submenu does not inherit a parent callback");
const nestedLeaf = anima.submenu.options.find((item) => item.has_submenu).submenu.options[0];
assert(nestedLeaf.s1LoraName === "Anima/sub/nested.safetensors", "multi-level leaves keep the full path");

// LiteGraph 1.57.6 ContextMenu.addItem inner_onclick:
//   1. options.callback(value) if set (menu-level)
//   2. value.callback(value) if value is an object and ignore_item_callbacks is not set
//   3. if value.submenu, new ContextMenu(submenu.options, { callback: submenu.callback, parentMenu })
// close() may trigger pointerleave on parentMenu but does not re-invoke the
// parent options.callback with the leaf. Opening a folder does invoke the
// parent options.callback with the folder item first.
function liteGraph1576InnerOnClick(item, menuCallback, extras) {
  const parentMenuCallback = extras && extras.parentMenuCallback;
  const parentItem = extras && extras.parentItem;
  // Replay the folder click that opened this submenu (parent menu callback
  // with the folder item). This must not consume a real pick.
  if (typeof parentMenuCallback === "function" && parentItem) parentMenuCallback(parentItem);
  if (typeof menuCallback === "function") menuCallback(item);
  if (item && typeof item === "object" && typeof item.callback === "function") item.callback(item);
}

let rootCalls = 0;
const rawNested = anima.submenu.options.find((item) => item.has_submenu).submenu.options[0];
liteGraph1576InnerOnClick(rawNested, anima.submenu.callback, {
  parentMenuCallback: () => { rootCalls += 1; },
  parentItem: anima,
});
assert(rootCalls === 1, "opening a nested menu invokes the parent callback with the folder");
assert(anima.submenu.callback === undefined, "raw submenu has no menu callback, so the leaf itself adds nothing");

const wiredMenu = withLoraChooserCallback(rawMenu, () => {});
const wiredAnima = wiredMenu.find((item) => item.has_submenu);
assert(typeof wiredAnima.submenu.callback === "function", "injected callback is copied onto the first submenu");
assert(typeof wiredAnima.submenu.options.find((item) => item.has_submenu).submenu.callback === "function", "injected callback is copied onto nested submenus");
const wiredNested = wiredAnima.submenu.options.find((item) => item.has_submenu).submenu.options[0];
assert(wiredNested.s1LoraName === "Anima/sub/nested.safetensors", "nested leaf keeps the full path");
assert(wiredNested.callback === undefined, "leaves do not also get item.callback (that would double-fire)");
const wiredRoot = wiredMenu.find((item) => item.s1LoraName === "root.safetensors");
assert(wiredRoot && wiredRoot.callback === undefined, "root leaves also have no item.callback");

function chooserSession(action, start, index) {
  let loras = Array.isArray(start) ? start.map((row) => ({ ...row })) : [];
  const onPick = makeLoraChooserPickCallback((picked) => {
    const result = applyLoraChooserAction(loras, action, picked, index);
    if (result.changed) loras = result.loras;
  });
  const items = withLoraChooserCallback(loraChooserMenuItems(nestedNames), onPick);
  return { onPick, items, loras: () => loras };
}

const rootSession = chooserSession("add", []);
const rootLeaf = rootSession.items.find((item) => item.s1LoraName === "root.safetensors");
liteGraph1576InnerOnClick(rootLeaf, rootSession.onPick);
assert(rootSession.loras().length === 1 && rootSession.loras()[0].name === "root.safetensors", "root pick through menu callback adds exactly one row");
// Force the 1.57.6 double-call (menu + item) against the once-guard.
const rootAgain = chooserSession("add", []);
const rootLeafAgain = { ...rootAgain.items.find((item) => item.s1LoraName === "root.safetensors"), callback: rootAgain.onPick };
liteGraph1576InnerOnClick(rootLeafAgain, rootAgain.onPick);
assert(rootAgain.loras().length === 1, "once-guard still adds only one row if item.callback also fires");

const subSession = chooserSession("add", []);
const subAnima = subSession.items.find((item) => item.has_submenu);
const subLeaf = subAnima.submenu.options.find((item) => item.s1LoraName && item.s1LoraName.includes("anima-turbo"));
liteGraph1576InnerOnClick(subLeaf, subAnima.submenu.callback, {
  parentMenuCallback: subSession.onPick,
  parentItem: subAnima,
});
assert(subSession.loras().length === 1 && subSession.loras()[0].name === "Anima/anima-turbo-lora-v0.2.safetensors", "subfolder pick adds exactly one row after parent folder callback");

const nestSession = chooserSession("add", []);
const nestAnima = nestSession.items.find((item) => item.has_submenu);
const nestFolder = nestAnima.submenu.options.find((item) => item.has_submenu);
const nestLeaf = nestFolder.submenu.options[0];
liteGraph1576InnerOnClick(nestLeaf, nestFolder.submenu.callback, {
  parentMenuCallback: nestSession.onPick,
  parentItem: nestFolder,
});
assert(nestSession.loras().length === 1 && nestSession.loras()[0].name === "Anima/sub/nested.safetensors", "multi-level pick adds exactly one row");
// Same leaf click with both menu and item callbacks plus parent folder fire.
const nestBoth = chooserSession("add", []);
const nestBothAnima = nestBoth.items.find((item) => item.has_submenu);
const nestBothFolder = nestBothAnima.submenu.options.find((item) => item.has_submenu);
const nestBothLeaf = { ...nestBothFolder.submenu.options[0], callback: nestBoth.onPick };
liteGraph1576InnerOnClick(nestBothLeaf, nestBothFolder.submenu.callback, {
  parentMenuCallback: nestBoth.onPick,
  parentItem: nestBothFolder,
});
assert(nestBoth.loras().length === 1, "nested once-guard adds one row even if menu and item callbacks both fire");

const swapSession = chooserSession("swap", [{ name: "root.safetensors", enabled_default: true, strength_model: 1, strength_clip: 1 }], 0);
const swapAnima = swapSession.items.find((item) => item.has_submenu);
const swapLeaf = { ...swapAnima.submenu.options.find((item) => item.s1LoraName && item.s1LoraName.includes("anima-turbo")), callback: swapSession.onPick };
liteGraph1576InnerOnClick(swapLeaf, swapAnima.submenu.callback, {
  parentMenuCallback: swapSession.onPick,
  parentItem: swapAnima,
});
assert(swapSession.loras().length === 1 && swapSession.loras()[0].name === "Anima/anima-turbo-lora-v0.2.safetensors", "swap through the 1.57.6 click sequence fires once");

const addedNested = applyLoraChooserAction([], "add", { s1LoraName: "Anima/sub/nested.safetensors", content: "nested.safetensors" });
assert(addedNested.changed && addedNested.loras[0].name === "Anima/sub/nested.safetensors", "adding a multi-level folder pick stores the full path");
assert(addedNested.row.enabled_default === true && addedNested.row.strength_model === 1, "nested add still uses default-on and 1.00");
const addedSlash = applyLoraChooserAction([], "add", "Anima\\anima-turbo-lora-v0.2.safetensors");
assert(addedSlash.changed && addedSlash.loras[0].name === "Anima/anima-turbo-lora-v0.2.safetensors", "add normalizes backslash separators");
const swappedNested = applyLoraChooserAction(addedNested.loras, "swap", { s1LoraName: "Anima\\anima-turbo-lora-v0.2.safetensors" }, 0);
assert(swappedNested.changed && swappedNested.loras[0].name === "Anima/anima-turbo-lora-v0.2.safetensors", "swap of a folder pick stores the normalized full path");
assert(swappedNested.loras.length === 1, "swap does not add a row");
const cancelledNested = applyLoraChooserAction(addedNested.loras, "add", { has_submenu: true, content: "📁 Anima" });
assert(!cancelledNested.changed && cancelledNested.loras.length === 1, "picking a folder item still adds no row");
assert(!applyLoraChooserAction(addedNested.loras, "add", "").changed, "cancel / empty pick still adds no row");

console.log("ok");
"""


def plan_theme_ids(entries):
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node is not installed")
    script = (
        "import { planThemeIds } from './js/s1_model.js';\n"
        "const plan = planThemeIds(JSON.parse(process.argv[1]));\n"
        "process.stdout.write(JSON.stringify(plan));\n"
    )
    completed = subprocess.run(
        [node, "--input-type=module", "--eval", script, json.dumps(entries)],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)
    return json.loads(completed.stdout)


class NodeTests(unittest.TestCase):
    def _settings(self, **overrides):
        node = PKG.NODE_CLASS_MAPPINGS["S1Settings"]()
        values = {
            "api_key": "",
            "api_model": "",
            "endpoint": CLIENT.DEFAULT_ENDPOINT,
            "noul_threshold": 0.5,
            "on_error": "passthrough",
            "min_confidence": 0.0,
        }
        values.update(overrides)
        (settings,) = node.build(**values)
        return settings

    def test_registration_and_widget_order(self):
        mappings = PKG.NODE_CLASS_MAPPINGS
        self.assertEqual(
            set(mappings),
            {
                "S1LoraLibrary",
                "S1Settings",
                "S1ThemeRoot",
                "S1Theme",
                "S1ThemeCollect",
                "S1LoraAggregate",
                "S1SaveImageScrubbed",
            },
        )
        self.assertEqual(
            PKG.NODE_DISPLAY_NAME_MAPPINGS,
            {
                "S1LoraLibrary": "LoRA Library",
                "S1Settings": "SystemOne Settings",
                "S1ThemeRoot": "Theme Root",
                "S1Theme": "Theme",
                "S1ThemeCollect": "Theme Collect",
                "S1LoraAggregate": "LoRA Aggregate",
                "S1SaveImageScrubbed": "S1 Save Image (Scrubbed)",
            },
        )
        self.assertEqual(PKG.WEB_DIRECTORY, "./js")
        for node in mappings.values():
            self.assertEqual(node.CATEGORY, "SystemOne/LoraRouter")

        root = mappings["S1ThemeRoot"]
        theme = mappings["S1Theme"]
        slot_types = ("S1_DECISION",) * TYPES.MAX_OPTION_OUTPUTS + ("STRING",)
        slot_names = tuple(
            f"option_{index + 1}" for index in range(TYPES.MAX_OPTION_OUTPUTS)
        ) + ("report_json",)
        self.assertEqual(TYPES.MAX_OPTION_OUTPUTS, 32)
        self.assertEqual(TYPES.REPORT_OUTPUT_INDEX, 32)
        for node in (root, theme):
            self.assertEqual(node.FUNCTION, "decide")
            self.assertEqual(node.RETURN_TYPES, slot_types)
            self.assertEqual(node.RETURN_NAMES, slot_names)
            inputs = node.INPUT_TYPES()
            required = inputs["required"]
            optional = inputs["optional"]
            self.assertIn("positive", required)
            self.assertNotIn("negative", required)
            self.assertIn("negative", optional)
            self.assertTrue(required["positive"][1]["forceInput"])
            self.assertTrue(optional["negative"][1]["forceInput"])
            self.assertEqual(optional["negative"][1].get("default"), "")
            self.assertEqual(required["settings"][0], "S1_SETTINGS")
            self.assertTrue(required["settings"][1]["forceInput"])
            self.assertFalse(required["theme_json"][1]["dynamicPrompts"])
            self.assertEqual(required["theme_json"][1]["default"], TYPES.EMPTY_THEME_JSON)
            for banned in ("run", "enable_json", "api_key", "api_model", "endpoint", "on_error"):
                self.assertNotIn(banned, required)
                self.assertNotIn(banned, optional)
            self.assertIn("visual editor", node.DESCRIPTION.lower())
            self.assertIn("Positive is the input above negative", node.DESCRIPTION)
            self.assertIn("optional", node.DESCRIPTION.lower())
        self.assertEqual(
            list(root.INPUT_TYPES()["required"]),
            ["positive", "settings", "theme_json"],
        )
        self.assertEqual(list(root.INPUT_TYPES()["optional"]), ["negative"])
        self.assertEqual(
            list(theme.INPUT_TYPES()["required"]),
            ["positive", "settings", "upstream", "theme_json"],
        )
        self.assertEqual(list(theme.INPUT_TYPES()["optional"]), ["negative"])
        self.assertEqual(theme.INPUT_TYPES()["required"]["upstream"][0], "S1_DECISION")
        self.assertIn("ExecutionBlocker", theme.DESCRIPTION)
        self.assertNotIn("when_upstream", theme.DESCRIPTION)
        signature = inspect.signature(root.decide)
        params = list(signature.parameters)
        self.assertEqual(params[params.index("positive") + 1], "negative")
        self.assertEqual(signature.parameters["negative"].default, "")

        settings = mappings["S1Settings"]
        self.assertEqual(settings.RETURN_TYPES, ("S1_SETTINGS",))
        self.assertEqual(settings.RETURN_NAMES, ("settings",))
        self.assertEqual(
            list(settings.INPUT_TYPES()["required"]),
            [
                "api_key",
                "api_model",
                "endpoint",
                "noul_threshold",
                "on_error",
                "min_confidence",
            ],
        )
        self.assertEqual(
            settings.INPUT_TYPES()["required"]["endpoint"][1]["default"],
            CLIENT.DEFAULT_ENDPOINT,
        )
        self.assertEqual(settings.INPUT_TYPES()["required"]["on_error"][1]["default"], "passthrough")
        built = self._settings(api_key="sekret-token-xyz", on_error="raise", noul_threshold=0.4)
        self.assertNotIn("sekret-token-xyz", repr(built))
        self.assertIn("api_key=set", repr(built))
        self.assertEqual(built.on_error, "raise")
        self.assertEqual(built.noul_threshold, 0.4)

        library = mappings["S1LoraLibrary"]
        self.assertEqual(library.RETURN_TYPES, ("S1_LORA_LIB",))
        self.assertEqual(
            library.INPUT_TYPES()["required"]["library_json"][1]["default"],
            TYPES.EMPTY_LORA_LIBRARY_JSON,
        )
        self.assertFalse(library.INPUT_TYPES()["required"]["library_json"][1]["dynamicPrompts"])

        collect = mappings["S1ThemeCollect"]
        self.assertEqual(collect.FUNCTION, "merge")
        self.assertEqual(collect.RETURN_TYPES, ("S1_DECISION",))
        self.assertEqual(collect.RETURN_NAMES, ("decision",))
        self.assertEqual(list(collect.INPUT_TYPES()["required"]), [])
        self.assertEqual(list(collect.INPUT_TYPES()["optional"])[:2], ["a", "b"])
        self.assertEqual(len(collect.INPUT_TYPES()["optional"]), 16)
        self.assertEqual(list(collect.INPUT_TYPES()["optional"])[2], "c")
        self.assertEqual(collect.INPUT_TYPES()["optional"]["a"][0], "S1_DECISION")
        self.assertTrue(collect.INPUT_TYPES()["optional"]["a"][1]["forceInput"])
        self.assertTrue(collect.INPUT_TYPES()["optional"]["b"][1]["forceInput"])
        self.assertIn("ExecutionBlocker", collect.DESCRIPTION)
        self.assertIn("optional", collect.DESCRIPTION.lower())
        self.assertIn("SchemaError", collect.DESCRIPTION)
        self.assertTrue(collect.IGNORE_OPTIONAL_EXECUTION_BLOCKERS)

        aggregate = mappings["S1LoraAggregate"]
        self.assertEqual(aggregate.FUNCTION, "apply")
        self.assertEqual(aggregate.RETURN_TYPES, ("MODEL", "CLIP", "STRING"))
        self.assertEqual(list(aggregate.INPUT_TYPES()["required"]), ["model", "lora_lib", "decision"])
        self.assertEqual(aggregate.INPUT_TYPES()["required"]["decision"][0], "S1_DECISION")
        self.assertNotIn("theme_result", aggregate.INPUT_TYPES()["required"])
        self.assertEqual(set(aggregate.INPUT_TYPES()["optional"]), {"clip", "on_error"})
        self.assertFalse((ROOT / "sequence_engine.py").exists())
        self.assertFalse((ROOT / "nodes" / "theme_library.py").exists())
        self.assertFalse((ROOT / "nodes" / "theme_sequence.py").exists())
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("s1_lora_router.sequence_engine")

    def test_root_option_slots_child_aggregate_and_unselected_skip(self):
        secret = "sekret-token-xyz"
        settings = self._settings(api_key=secret, api_model="my-model")
        library_node = PKG.NODE_CLASS_MAPPINGS["S1LoraLibrary"]()
        (library,) = library_node.build(read_example("lora_library.minimal.json"))
        root = PKG.NODE_CLASS_MAPPINGS["S1ThemeRoot"]()
        child = PKG.NODE_CLASS_MAPPINGS["S1Theme"]()
        aggregate = PKG.NODE_CLASS_MAPPINGS["S1LoraAggregate"]()
        collect = PKG.NODE_CLASS_MAPPINGS["S1ThemeCollect"]()
        seen = []

        def urlopen(req, timeout=None):
            seen.append(payload_from_request(req)["state"])
            return canned_urlopen(req, timeout)

        with mock.patch("urllib.request.urlopen", side_effect=urlopen):
            art = root.decide(
                positive="anime girl",
                negative="blurry",
                settings=settings,
                theme_json=read_example("theme.art_style.json"),
            )
            pack = child.decide(
                positive="child",
                negative="",
                settings=settings,
                theme_json=read_example("theme.character_pack.json"),
                upstream=art[0],
            )
        self.assertEqual(seen[0], {"positive": "anime girl", "negative": "blurry"})
        self.assertEqual(seen[1], {"positive": "child", "negative": ""})
        self.assertEqual(len(art), 33)
        anime, realistic, none_slot = art[0], art[1], art[2]
        self.assertEqual(anime.slot_option_id, "anime")
        self.assertEqual(anime.emitted_reason, "selected")
        self.assertEqual(anime.result.get("art_style").selected, ["anime"])
        self.assertEqual(anime.result.tags, ["style_anime"])
        self.assertTrue(BLOCKER.is_execution_blocker(realistic))
        self.assertIsNone(realistic.message)
        self.assertTrue(BLOCKER.is_execution_blocker(none_slot))
        self.assertTrue(BLOCKER.is_execution_blocker(art[3]))
        self.assertNotIn(secret, art[-1])
        art_report = json.loads(art[-1])
        self.assertEqual(art_report["role"], "root")
        self.assertEqual(art_report["slots"][0], {"option_id": "anime", "emitted": "selected"})
        self.assertEqual(art_report["slots"][1]["emitted"], "blocked")
        self.assertEqual(pack[0].slot_option_id, "waifu_a")
        self.assertEqual(pack[1].slot_option_id, "waifu_b")
        self.assertIs(pack[0].result, pack[1].result)
        self.assertEqual(pack[0].result.tags, ["style_anime", "char_a", "char_b"])
        self.assertNotIn(secret, pack[-1])

        with mock.patch("urllib.request.urlopen") as skipped_call:
            blocked = child.decide(
                positive="child",
                negative="",
                settings=settings,
                theme_json="{",
                upstream=realistic,
            )
        skipped_call.assert_not_called()
        self.assertTrue(all(BLOCKER.is_execution_blocker(item) for item in blocked[:-1]))
        blocked_report = json.loads(blocked[-1])
        self.assertEqual(blocked_report["status"], "blocked")
        self.assertFalse(blocked_report["api"]["called"])
        self.assertNotIn(secret, blocked[-1])

        model = object()
        out_model, out_clip, agg_report = aggregate.apply(model, library, pack[0])
        self.assertIs(out_model, model)
        self.assertIsNone(out_clip)
        parsed = json.loads(agg_report)
        self.assertEqual([item["lora_id"] for item in parsed["applied"]], ["char_a", "style_anime_v3"])
        self.assertEqual(parsed["matched"][1]["strength_model"], 0.8)
        self.assertNotEqual(parsed["matched"][1]["strength_model"], 0.85)

        (shared,) = collect.merge(art[0], pack[0])
        self.assertEqual(shared.emitted_reason, "collected")
        self.assertEqual(
            [item.theme_id for item in shared.result.decisions],
            ["art_style", "character_pack"],
        )
        self.assertEqual(shared.result.tags, ["style_anime", "char_a", "char_b"])
        self.assertEqual(
            [item.theme_id for item in shared.result.decisions].count("art_style"),
            1,
        )

        with mock.patch("urllib.request.urlopen", side_effect=urlopen):
            left = root.decide(
                positive="",
                negative="",
                settings=settings,
                theme_json=json.dumps(theme_doc(theme_id="left", options=[option("a", ["ta"])])),
            )
            right = root.decide(
                positive="",
                negative="",
                settings=settings,
                theme_json=json.dumps(theme_doc(theme_id="right", options=[option("b", ["tb"])])),
            )
        (merged,) = collect.merge(left[0], right[0])
        self.assertEqual([item.theme_id for item in merged.result.decisions], ["left", "right"])

        with mock.patch("urllib.request.urlopen", side_effect=urlopen):
            omitted = root.decide(
                positive="p",
                settings=settings,
                theme_json=json.dumps(theme_doc(theme_id="omit_neg", options=[option("a", ["ta"])])),
            )
        self.assertEqual(omitted[0].slot_option_id, "a")
        self.assertEqual(omitted[0].result.tags, ["ta"])
        (only_a,) = collect.merge(art[0])
        self.assertIs(only_a, art[0])
        (only_b,) = collect.merge(b=pack[0])
        self.assertIs(only_b, pack[0])
        (blocked_ignored,) = collect.merge(art[0], realistic)
        self.assertIs(blocked_ignored, art[0])
        (blocked_first,) = collect.merge(realistic, pack[0])
        self.assertIs(blocked_first, pack[0])
        with self.assertRaises(TYPES.SchemaError) as collect_empty:
            collect.merge()
        self.assertIn("at least one input", str(collect_empty.exception))
        with self.assertRaises(TYPES.SchemaError):
            collect.merge(realistic, art[3])

        with mock.patch("urllib.request.urlopen") as empty_call:
            empty = root.decide(
                positive="",
                negative="",
                settings=settings,
                theme_json=read_example("theme.empty.json"),
            )
        empty_call.assert_not_called()
        self.assertEqual(empty[0].slot_option_id, "none")
        self.assertEqual(empty[0].emitted_reason, "selected")
        self.assertEqual(empty[0].result.tags, [])
        self.assertTrue(all(BLOCKER.is_execution_blocker(item) for item in empty[1:-1]))
        self.assertNotIn(secret, empty[-1])

        with mock.patch("urllib.request.urlopen") as bad_json:
            with self.assertRaises(TYPES.SchemaError):
                root.decide(
                    positive="",
                    negative="",
                    settings=settings,
                    theme_json="{",
                )
        bad_json.assert_not_called()
        with self.assertRaises(TYPES.SchemaError) as upstream_error:
            child.decide(
                positive="",
                negative="",
                settings=settings,
                theme_json="{",
                upstream=object(),
            )
        self.assertIn("S1_DECISION", str(upstream_error.exception))

    def test_none_emits_without_tags_and_a_child_still_runs(self):
        settings = self._settings(api_key="k")
        root = PKG.NODE_CLASS_MAPPINGS["S1ThemeRoot"]()
        child = PKG.NODE_CLASS_MAPPINGS["S1Theme"]()

        def none_choice(req, timeout=None):
            body = payload_from_request(req)
            answers = {
                qid: {"choice": "none", "confidence": 1}
                for qid, question in body["questions"].items()
                if question["type"] == "choice"
            }
            return FakeHTTPResponse({"answers": answers})

        with mock.patch("urllib.request.urlopen", side_effect=none_choice):
            art = root.decide(
                positive="plain photo",
                negative="",
                settings=settings,
                theme_json=read_example("theme.art_style.json"),
            )
        none_slot = art[2]
        self.assertEqual(none_slot.slot_option_id, "none")
        self.assertEqual(none_slot.emitted_reason, "selected")
        self.assertEqual(none_slot.result.tags, [])
        self.assertNotIn("should_not_apply", none_slot.result.tags)
        self.assertTrue(BLOCKER.is_execution_blocker(art[0]))
        def only_choice(req, timeout=None):
            body = payload_from_request(req)
            answers = {
                qid: {"choice": "only", "confidence": 1}
                for qid, question in body["questions"].items()
                if question["type"] == "choice"
            }
            return FakeHTTPResponse({"answers": answers})

        with mock.patch("urllib.request.urlopen", side_effect=only_choice):
            followed = child.decide(
                positive="still here",
                negative="",
                settings=settings,
                theme_json=json.dumps(theme_doc(theme_id="after_none", options=[option("only", ["extra"])])),
                upstream=none_slot,
            )
        self.assertEqual(followed[0].result.tags, ["extra"])
        self.assertEqual(followed[0].result.get("art_style").selected, ["none"])

    def test_on_error_passthrough_emits_every_slot_and_raise_stops(self):
        root = PKG.NODE_CLASS_MAPPINGS["S1ThemeRoot"]()
        doc = json.dumps(theme_doc(theme_id="bad_choice", options=[option("a"), option("b")]))

        def bad_choice(req, timeout=None):
            body = payload_from_request(req)
            answers = {
                qid: {"choice": "nope", "confidence": 1}
                for qid, question in body["questions"].items()
                if question["type"] == "choice"
            }
            return FakeHTTPResponse({"answers": answers})

        with mock.patch("urllib.request.urlopen", side_effect=bad_choice):
            passed = root.decide(
                positive="p",
                negative="n",
                settings=self._settings(api_key="k", on_error="passthrough"),
                theme_json=doc,
            )
        self.assertEqual(passed[0].emitted_reason, "passthrough_error")
        self.assertEqual(passed[1].emitted_reason, "passthrough_error")
        self.assertIs(passed[0].result, passed[1].result)
        self.assertEqual(passed[0].result.tags, [])
        self.assertEqual(passed[2].emitted_reason, "passthrough_error")
        self.assertTrue(BLOCKER.is_execution_blocker(passed[3]))
        self.assertTrue(any("passthrough" in note for note in json.loads(passed[-1])["notes"]))

        with mock.patch("urllib.request.urlopen", side_effect=bad_choice):
            with self.assertRaises(ENGINE.ThemeError):
                root.decide(
                    positive="p",
                    negative="n",
                    settings=self._settings(api_key="k", on_error="raise"),
                    theme_json=doc,
                )

    def test_more_than_32_options_fail_before_http(self):
        root = PKG.NODE_CLASS_MAPPINGS["S1ThemeRoot"]()
        options = [option(f"o{index}") for index in range(33)]
        doc = json.dumps(theme_doc(theme_id="wide", select_mode="multi", options=options))
        with mock.patch("urllib.request.urlopen") as urlopen:
            with self.assertRaises(TYPES.SchemaError) as ctx:
                root.decide(
                    positive="p",
                    negative="",
                    settings=self._settings(api_key="k"),
                    theme_json=doc,
                )
        urlopen.assert_not_called()
        self.assertIn("32", str(ctx.exception))

    def test_multi_with_no_selection_blocks_every_slot(self):
        root = PKG.NODE_CLASS_MAPPINGS["S1ThemeRoot"]()

        def low_scores(req, timeout=None):
            body = payload_from_request(req)
            answers = {qid: {"noul": 0.1} for qid in body["questions"]}
            return FakeHTTPResponse({"answers": answers})

        with mock.patch("urllib.request.urlopen", side_effect=low_scores):
            pack = root.decide(
                positive="nobody",
                negative="",
                settings=self._settings(api_key="k"),
                theme_json=read_example("theme.character_pack.json"),
            )
        self.assertTrue(BLOCKER.is_execution_blocker(pack[0]))
        self.assertTrue(BLOCKER.is_execution_blocker(pack[1]))
        report = json.loads(pack[-1])
        self.assertEqual(report["selected"], [])
        self.assertEqual(report["accumulated_tags"], [])
        self.assertTrue(any("every option slot is blocked" in note for note in report["notes"]))

    def test_aggregate_node_passthrough_and_raise(self):
        node = PKG.NODE_CLASS_MAPPINGS["S1LoraAggregate"]()
        model = object()
        clip = object()
        out_model, out_clip, report = node.apply(model, "nope", "nope", clip=clip, on_error="passthrough")
        self.assertIs(out_model, model)
        self.assertIs(out_clip, clip)
        parsed = json.loads(report)
        self.assertTrue(parsed["errors"])
        self.assertIn("passthrough", " ".join(parsed["notes"]))
        with self.assertRaises(TYPES.SchemaError):
            node.apply(model, "nope", "nope", on_error="raise")

        library = lora_entries({"lora_id": "L", "name": "missing.safetensors", "tags": ["only_tag"]})
        outcome = run_theme(
            theme_json=theme_doc(options=[option("only", ["only_tag"])]),
            client=CountingClient(),
        )
        result = (as_payload(outcome.result, slot_option_id="only"),)

        def missing_api():
            return (
                (
                    lambda *_args: (_ for _ in ()).throw(AssertionError("must not patch")),
                    lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not load")),
                    lambda *_args: None,
                ),
                None,
            )

        original = APPLY._import_comfy
        APPLY._import_comfy = missing_api
        try:
            passed_model, passed_clip, passed_report = node.apply(
                model, library, result[0], on_error="passthrough"
            )
            self.assertIs(passed_model, model)
            self.assertIsNone(passed_clip)
            self.assertIn("missing.safetensors", json.loads(passed_report)["errors"][0])
            with self.assertRaises(APPLY.ApplyError):
                node.apply(model, library, result[0], on_error="raise")
        finally:
            APPLY._import_comfy = original

    def test_planned_theme_ids_run_as_a_unique_chain(self):
        def factory(tag, title):
            return json.dumps(
                {
                    "version": 1,
                    "theme_id": "theme_1",
                    "title": title,
                    "instructions": "I",
                    "select_mode": "single",
                    "options": [
                        {
                            "option_id": "yes",
                            "label": "y",
                            "description": "",
                            "tags": [tag],
                        }
                    ],
                }
            )

        empty = json.dumps({"version": 1, "match": "any", "clauses": []})
        watch = json.dumps(
            {
                "version": 1,
                "match": "any",
                "clauses": [
                    {"theme_id": "theme_1", "op": "includes_any", "option_ids": ["yes"]}
                ],
            }
        )
        entries = [
            {"key": "a", "origin": "new", "themeJson": factory("ta", "A"), "enableJson": empty},
            {"key": "b", "origin": "new", "themeJson": factory("tb", "B"), "enableJson": watch},
            {"key": "c", "origin": "duplicate", "themeJson": factory("tc", "C"), "enableJson": watch},
        ]
        plan = plan_theme_ids(entries)
        by_key = {item["key"]: item for item in plan["assignments"]}
        self.assertEqual(
            [by_key[key]["themeId"] for key in ("a", "b", "c")],
            ["theme_1", "theme_2", "theme_3"],
        )
        self.assertEqual(plan["conflicts"], [])
        self.assertEqual(by_key["b"]["enableJson"], watch)
        self.assertEqual(by_key["c"]["enableJson"], watch)
        self.assertNotIn("theme_3", by_key["c"]["enableJson"])
        second = plan_theme_ids(
            [
                {
                    "key": item["key"],
                    "origin": "new",
                    "themeJson": item["themeJson"],
                    "enableJson": item["enableJson"],
                }
                for item in plan["assignments"]
            ]
        )
        self.assertTrue(all(not item["changed"] for item in second["assignments"]))
        self.assertEqual(
            [item["themeId"] for item in second["assignments"]],
            ["theme_1", "theme_2", "theme_3"],
        )

        settings = self._settings(api_key="k")
        root = PKG.NODE_CLASS_MAPPINGS["S1ThemeRoot"]()
        child = PKG.NODE_CLASS_MAPPINGS["S1Theme"]()

        def yes_choice(req, timeout=None):
            body = payload_from_request(req)
            answers = {
                qid: {"choice": "yes", "confidence": 1}
                for qid, question in body["questions"].items()
                if question["type"] == "choice"
            }
            return FakeHTTPResponse({"answers": answers})

        with mock.patch("urllib.request.urlopen", side_effect=yes_choice):
            first = root.decide(
                positive="p",
                negative="",
                settings=settings,
                theme_json=by_key["a"]["themeJson"],
            )
            second_out = child.decide(
                positive="p",
                negative="",
                settings=settings,
                theme_json=by_key["b"]["themeJson"],
                upstream=first[0],
            )
            third = child.decide(
                positive="p",
                negative="",
                settings=settings,
                theme_json=by_key["c"]["themeJson"],
                upstream=second_out[0],
            )
        result = third[0].result
        self.assertEqual(
            [item.theme_id for item in result.decisions],
            ["theme_1", "theme_2", "theme_3"],
        )
        self.assertTrue(all(item.status == "ok" for item in result.decisions))
        self.assertEqual([item.selected for item in result.decisions], [["yes"], ["yes"], ["yes"]])
        self.assertEqual(result.tags, ["ta", "tb", "tc"])
        self.assertTrue(json.loads(first[-1])["api"]["called"])

    def test_docs_describe_the_break(self):
        needles = (
            "S1ThemeRoot",
            "S1Settings",
            "S1_DECISION",
            "ExecutionBlocker",
            "enable_json",
            "theme_result",
            "S1ThemeCollect",
            "none_option_id",
            "S1Theme",
        )
        for name in ("README.md", "SPEC.md", "MIGRATION.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            for needle in needles:
                self.assertIn(needle, text, f"{name} missing {needle}")
            self.assertIn("Positive is the input above negative", text)
            self.assertLess(text.index("Positive is the input above negative"), text.lower().index("negative"))
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        lowered = readme.lower()
        self.assertIn("sidebar tab is gone", lowered)
        self.assertIn("no apply to node", lowered)
        self.assertIn("32", readme)
        migration = (ROOT / "MIGRATION.md").read_text(encoding="utf-8")
        self.assertIn("lora_bindings", migration)
        self.assertIn("S1ThemeSequence", migration)
        self.assertIn("run", migration)
        spec = (ROOT / "SPEC.md").read_text(encoding="utf-8")
        self.assertIn("passthrough", spec)
        self.assertIn("every option slot", spec.lower())

    def test_editor_is_modal_only_and_model_checks_pass(self):
        editors = (ROOT / "js" / "s1_editors.js").read_text(encoding="utf-8")
        model_js = (ROOT / "js" / "s1_model.js").read_text(encoding="utf-8")
        combined = (editors + "\n" + model_js).lower()
        self.assertNotIn("registersidebartab", combined)
        self.assertNotIn("sidebar", combined)
        self.assertNotIn("s1 editors", combined)
        self.assertNotIn("apply to node", editors.lower())
        self.assertNotIn("reload from node", editors.lower())
        self.assertIn('name: "SystemOne.LoraRouter.UI"', editors)
        self.assertIn("Open visual editor", editors)
        self.assertIn("const WRITE_DELAY_MS = 220;", editors)
        self.assertIn("const POLL_MS = 500;", editors)
        self.assertIn("s1-invalid", editors)
        self.assertIn("function scheduleLiveWrite(", editors)
        self.assertIn("function liveWrite(", editors)
        self.assertIn("function pollWidgets(", editors)
        self.assertIn("function applyInvalidMarks(", editors)
        self.assertIn("function syncOptionOutputs(", editors)
        self.assertIn("serialize: false", editors)
        self.assertIn('from "../../scripts/api.js"', editors)
        self.assertIn("/object_info/LoraLoader", editors)
        self.assertIn("/object_info/LoraLoaderModelOnly", editors)
        self.assertIn('"/object_info"', editors)
        self.assertIn("/models/loras", editors)
        self.assertIn("Browse loras", editors)
        self.assertIn("Needs a running ComfyUI.", editors)
        self.assertIn("Typed names still work.", editors)
        self.assertIn("lora_id", editors)
        self.assertIn("theme_id and option_id are assigned automatically", editors)
        self.assertIn("The last option is ${DEFAULT_NONE_LABEL}", editors)
        self.assertNotIn("預設啟用", editors)
        self.assertNotIn('field("lora_id"', editors)
        self.assertNotIn('field("theme_id"', editors)
        self.assertNotIn('field("option_id"', editors)
        self.assertNotIn('field("upstream theme_id"', editors)
        self.assertNotIn("promptField(", editors)
        self.assertIn("strength writes both strength_model and strength_clip", editors)
        self.assertIn("input.readOnly = true", editors)
        self.assertLess(
            editors.index("Positive is the input above negative"),
            editors.index("Prompts are not stored in theme_json"),
        )
        self.assertIn("contributes no tags", editors)
        self.assertIn("export function assignThemeDocument", model_js)
        self.assertIn("export function planThemeIds", model_js)
        self.assertIn("export function planOptionOutputs", model_js)
        self.assertIn("export function relinkOptionSlots", model_js)
        self.assertIn("export function orderThemePromptInputs", model_js)
        self.assertIn("orderThemePromptInputs", editors)
        self.assertNotIn("export function assignThemeIds", model_js)
        self.assertIn("planThemeIds", editors)
        self.assertIn("planOptionOutputs", editors)
        self.assertIn("relinkOptionSlots", editors)
        self.assertIn("beforeConfigureGraph()", editors)
        self.assertIn("loadedGraphNode(node)", editors)
        self.assertIn("afterConfigureGraph()", editors)
        self.assertIn('wrap("queuePrompt")', editors)
        self.assertIn('wrap("graphToPrompt")', editors)
        self.assertIn("serializeValue", editors)
        self.assertIn("s1ThemeRestored", editors)
        self.assertIn("theme_id conflict", editors)
        self.assertNotIn("set a unique id in the JSON widget", editors)
        self.assertNotIn("cannot see other Theme nodes", editors)
        self.assertIn("lora_bindings was removed; selected options contribute tags", model_js)
        self.assertIn("fallback_option_id was removed and is not applied", model_js)
        live = editors[editors.index("function liveWrite(") : editors.index("function pollWidgets(")]
        self.assertIn("syncOptionOutputs(state.node, ", live)
        self.assertNotIn("enable_json", live)
        self.assertNotIn("positive", live)
        self.assertNotIn("negative", live)
        self.assertIn("S1LoraLibrary", editors)
        self.assertIn("S1ThemeRoot", editors)
        self.assertIn("S1Theme", editors)
        self.assertNotIn("S1Settings", editors)
        self.assertIn("S1ThemeCollect", editors)
        self.assertIn("syncCollectInputs", editors)
        self.assertNotIn("S1LoraAggregate", editors)
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        self.assertIn("installLoraLibraryNode", editors)
        self.assertIn("installThemeNode", editors)
        self.assertIn("compactOptionOutputs", editors)
        self.assertIn("expandOptionOutputs", editors)
        self.assertIn("modal: false", editors)
        lora_node = (ROOT / "js" / "s1_lora_node.js").read_text(encoding="utf-8")
        self.assertIn("addDOMWidget", lora_node)
        self.assertNotIn("Toggle All", lora_node)
        self.assertIn("Default On", lora_node)
        self.assertNotIn("預設啟用", lora_node)
        self.assertNotIn("s1-lora-info", lora_node)
        self.assertNotIn("is-off", lora_node)
        self.assertIn("＋ Add Lora", lora_node)
        self.assertIn("showLoraChooser", lora_node)
        self.assertIn("withLoraChooserCallback", lora_node)
        self.assertIn("makeLoraChooserPickCallback", lora_node)
        self.assertIn("submenu.callback", lora_node)
        self.assertIn("export function withLoraChooserCallback", model_js)
        self.assertIn("export function makeLoraChooserPickCallback", model_js)
        self.assertIn("export function normalizeLoraPath", model_js)
        self.assertNotIn("next.callback = callback", model_js)
        self.assertIn('className: "dark"', lora_node)
        self.assertIn("LiteGraph", lora_node)
        self.assertIn("enabled_default", lora_node)
        self.assertIn("strength_clip = number", lora_node)
        self.assertIn("library_json", lora_node)
        self.assertIn("hideLibraryJsonWidget", lora_node)
        self.assertIn("mountTagChips", lora_node)
        theme_node = (ROOT / "js" / "s1_theme_node.js").read_text(encoding="utf-8")
        self.assertIn("addDOMWidget", theme_node)
        self.assertIn("Add option", theme_node)
        self.assertIn("Description Here", theme_node)
        self.assertIn("Tags (Comma)", theme_node)
        self.assertIn("hideThemeJsonWidget", theme_node)
        self.assertIn("mountTagChips", theme_node)
        self.assertIn("export function optionOutputLabels", model_js)
        self.assertIn("output.label = visible", model_js)
        self.assertIn("label || localized_name || name", model_js)
        self.assertIn("flex-wrap: wrap", (ROOT / "js" / "s1_tag_chips.js").read_text(encoding="utf-8"))
        self.assertNotIn("overflow-x: auto", (ROOT / "js" / "s1_tag_chips.js").read_text(encoding="utf-8"))
        self.assertNotIn("flex-wrap: nowrap", (ROOT / "js" / "s1_tag_chips.js").read_text(encoding="utf-8"))
        self.assertIn("nextEditorNodeSize", (ROOT / "js" / "s1_node_size.js").read_text(encoding="utf-8"))
        self.assertIn("getHeight", theme_node)
        self.assertIn("ResizeObserver", (ROOT / "js" / "s1_node_size.js").read_text(encoding="utf-8"))
        self.assertIn("showNodeOptions", (ROOT / "js" / "s1_row_menu.js").read_text(encoding="utf-8"))
        self.assertIn("bindRowContextMenu", theme_node)
        self.assertIn("bindRowContextMenu", lora_node)
        self.assertIn("stopImmediatePropagation", (ROOT / "js" / "s1_row_menu.js").read_text(encoding="utf-8"))
        self.assertIn("processContextMenu", (ROOT / "js" / "s1_row_menu.js").read_text(encoding="utf-8"))
        for name in ("s1_node_size.js", "s1_row_menu.js"):
            extra_check = subprocess.run(
                [node, "--check", str(ROOT / "js" / name)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(extra_check.returncode, 0, extra_check.stderr)
        chips = (ROOT / "js" / "s1_tag_chips.js").read_text(encoding="utf-8")
        self.assertIn("Enter", chips)
        self.assertIn("Backspace", chips)
        self.assertIn("×", chips)
        for name in ("s1_editors.js", "s1_model.js", "s1_lora_node.js", "s1_theme_node.js", "s1_tag_chips.js"):
            checked = subprocess.run(
                [node, "--check", str(ROOT / "js" / name)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)
        completed = subprocess.run(
            [node, "--input-type=module", "--eval", JS_MODEL],
            check=False,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("ok", completed.stdout)

    def test_comfyui_loader_style_import(self):
        script = (
            "import importlib.util, os, sys\n"
            "root = sys.argv[1]\n"
            "name = 's1_loader_check'\n"
            "init = os.path.join(root, '__init__.py')\n"
            "spec = importlib.util.spec_from_file_location(name, init, submodule_search_locations=[root])\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "sys.modules[name] = mod\n"
            "spec.loader.exec_module(mod)\n"
            "print(','.join(sorted(mod.NODE_CLASS_MAPPINGS)))\n"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script, str(ROOT)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout.strip(),
            "S1LoraAggregate,S1LoraLibrary,S1SaveImageScrubbed,S1Settings,S1Theme,S1ThemeCollect,S1ThemeRoot",
        )

    def test_top_level_nodes_package_imports(self):
        module = importlib.import_module("nodes")
        self.assertTrue(module.__doc__)


if __name__ == "__main__":
    unittest.main()
