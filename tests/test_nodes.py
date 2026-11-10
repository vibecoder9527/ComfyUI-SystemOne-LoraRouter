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
    FakeHTTPResponse,
    canned_urlopen,
    lora_entries,
    option,
    payload_from_request,
    read_example,
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
  relinkOptionSlots,
  orderThemePromptInputs,
  MAX_OPTION_OUTPUTS,
} from "./js/s1_model.js";

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
assert(planned.slots[1].name === "none" && planned.slots[1].type === "S1_DECISION", "second visible");
assert(planned.slots[2].hidden === true && planned.slots[2].name === "", "pad hidden");
assert(planned.reportIndex === 32, "report index");
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
assert(sibling.outputs[2].hidden === false && sibling.outputs[2].name === "·", "unused pad stays visible");

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
assert(linksOnly.outputs[2].hidden === false && linksOnly.outputs[2].name === "·", "unlinked pad is visible");

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
        self.assertEqual(list(collect.INPUT_TYPES()["optional"]), ["a", "b"])
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
        self.assertIn("a or b", str(collect_empty.exception))
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
        self.assertTrue(all(BLOCKER.is_execution_blocker(item) for item in empty[:-1]))
        self.assertIn("no option slots", empty[-1])
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
        self.assertTrue(BLOCKER.is_execution_blocker(passed[2]))
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
        theme = PKG.NODE_CLASS_MAPPINGS["S1ThemeRoot"]()
        result = theme.decide(
            positive="",
            negative="",
            settings=self._settings(api_key=""),
            theme_json=json.dumps(theme_doc(options=[option("only", ["only_tag"])])),
        )

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

        settings = self._settings(api_key="")
        root = PKG.NODE_CLASS_MAPPINGS["S1ThemeRoot"]()
        child = PKG.NODE_CLASS_MAPPINGS["S1Theme"]()
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
        self.assertFalse(json.loads(first[-1])["api"]["called"])

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
        self.assertIn('readOnlyLine("lora_id"', editors)
        self.assertIn('readOnlyLine("theme_id"', editors)
        self.assertIn('readOnlyLine("option_id"', editors)
        self.assertNotIn('field("lora_id"', editors)
        self.assertNotIn('field("theme_id"', editors)
        self.assertNotIn('field("option_id"', editors)
        self.assertNotIn('field("upstream theme_id"', editors)
        self.assertNotIn("promptField(", editors)
        self.assertIn("strength (model & clip)", editors)
        self.assertIn("input.readOnly = true", editors)
        self.assertLess(
            editors.index("Positive is the input above negative"),
            editors.index("Prompts are not stored in theme_json"),
        )
        self.assertIn("There is no fallback option.", editors)
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
        self.assertIn("syncOptionOutputs(state.node)", live)
        self.assertNotIn("enable_json", live)
        self.assertNotIn("positive", live)
        self.assertNotIn("negative", live)
        self.assertIn("S1LoraLibrary", editors)
        self.assertIn("S1ThemeRoot", editors)
        self.assertIn("S1Theme", editors)
        self.assertNotIn("S1Settings", editors)
        self.assertNotIn("S1ThemeCollect", editors)
        self.assertNotIn("S1LoraAggregate", editors)
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        for name in ("s1_editors.js", "s1_model.js"):
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
            "S1LoraAggregate,S1LoraLibrary,S1Settings,S1Theme,S1ThemeCollect,S1ThemeRoot",
        )

    def test_top_level_nodes_package_imports(self):
        module = importlib.import_module("nodes")
        self.assertTrue(module.__doc__)


if __name__ == "__main__":
    unittest.main()
