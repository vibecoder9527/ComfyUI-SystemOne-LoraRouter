// Theme option "swap position" ids: option_N is always table row N.
// Run: node tests/js/theme_reorder_ids.test.mjs  (tests/test_theme_reorder_ids.py runs it).
// Pure s1_model.js logic only; the browser UI is not exercised here.

import {
  addThemeOption,
  applyOptionIndexRemap,
  canonicalizeThemeOptions,
  compactOptionOutputs,
  deleteThemeOption,
  expandOptionOutputs,
  isCanonicalThemeOptions,
  moveThemeOption,
  optionDisplayOrder,
  parseEditorDocument,
  planOptionIndexRemap,
  planOptionOutputs,
  planThemeWrite,
  relinkOptionSlots,
  REPORT_OUTPUT_INDEX,
} from "../../js/s1_model.js";

let checks = 0;
function assert(cond, message) {
  checks += 1;
  if (!cond) {
    console.error(`FAIL: ${message}`);
    process.exit(1);
  }
}
const ids = (model) => model.options.map((option) => option.option_id).join(",");
const names = (model) => model.options.map((option) => option.label).join(",");

function theme(options, noneId, themeId = "theme_1") {
  const doc = { version: 1, theme_id: themeId, title: "Theme", instructions: "Choose.", select_mode: "single", options };
  if (noneId) doc.none_option_id = noneId;
  return doc;
}
function opt(id, label, tags) {
  const out = { option_id: id, label, description: label };
  if (tags) out.tags = tags;
  return out;
}

// Graph doubles. `store` mirrors frontend 1.57: graph.links is a Map,
// camelCase fields, output.links a setter that must never be assigned.
class StoreOutput {
  constructor(name, ids) {
    this.name = name;
    this.type = "S1_DECISION";
    this._ids = ids;
  }
  get links() { return this._ids; }
  set links(_value) { throw new Error("output.links assignment drops the wire on frontend 1.57"); }
}

function makeGraph({ map = false } = {}) {
  const targets = new Map();
  const removed = [];
  const graph = {
    links: map ? new Map() : {},
    _nodes: [],
    removed,
    addTarget(id, inputs) {
      const node = { id, inputs: Array.from({ length: inputs }, () => ({ link: null })) };
      targets.set(String(id), node);
      graph._nodes.push(node);
      return node;
    },
    getNodeById(id) { return targets.get(String(id)) || null; },
  };
  return graph;
}

function addLink(graph, { id, origin, slot, target, targetSlot, camel = false }) {
  const link = camel
    ? { id, originId: origin, originSlot: slot, targetId: target, targetSlot, type: "S1_DECISION" }
    : { id, origin_id: origin, origin_slot: slot, target_id: target, target_slot: targetSlot, type: "S1_DECISION" };
  if (graph.links instanceof Map) graph.links.set(id, link);
  else graph.links[id] = link;
  const node = graph.getNodeById(target);
  if (node) node.inputs[targetSlot].link = id;
  return link;
}

function getLink(graph, id) {
  return graph.links instanceof Map ? graph.links.get(id) : graph.links[id];
}
function originSlot(graph, id) {
  const link = getLink(graph, id);
  return link ? (link.origin_slot != null ? link.origin_slot : link.originSlot) : undefined;
}

function themeNode(id, doc, graph, { store = false } = {}) {
  const json = JSON.stringify(doc);
  const plan = planOptionOutputs(json);
  const outputs = [];
  for (let index = 0; index <= REPORT_OUTPUT_INDEX; index += 1) {
    const name = index === REPORT_OUTPUT_INDEX ? "report_json" : (plan.slots[index].name || "·");
    outputs.push(store ? new StoreOutput(name, []) : { name, type: index === REPORT_OUTPUT_INDEX ? "STRING" : "S1_DECISION", links: [] });
  }
  outputs[REPORT_OUTPUT_INDEX].type = "STRING";
  const node = { id, graph, outputs, widgets: [{ name: "theme_json", value: json }] };
  relinkOptionSlots(node, plan.slots);
  return node;
}

function wire(node, graph, slot, linkId, targetId, targetSlot = 0, camel = false) {
  if (!graph.getNodeById(targetId)) graph.addTarget(targetId, 4);
  addLink(graph, { id: linkId, origin: node.id, slot, target: targetId, targetSlot, camel });
  const output = node.outputs[slot];
  if (Array.isArray(output.links)) output.links.push(linkId);
}

// Same sequence as s1_theme_node.js writeTheme -> syncThemeOutputs.
function writeTheme(node, model) {
  const widget = node.widgets[0];
  const planned = planThemeWrite(widget.value, model);
  if (!planned.ok) return planned;
  widget.value = planned.json;
  const plan = planOptionOutputs(planned.json);
  expandOptionOutputs(node);
  const applied = planned.remap.ok && !planned.remap.identity ? applyOptionIndexRemap(node, planned.remap) : { moved: 0, removed: 0 };
  const relinked = relinkOptionSlots(node, plan.slots);
  compactOptionOutputs(node, JSON.parse(planned.json).none_option_id);
  return { ...planned, applied, relinked };
}
function readTheme(node) {
  const parsed = parseEditorDocument("theme", node.widgets[0].value);
  assert(parsed.ok, "widget json parses");
  return parsed.model;
}
// Expanded origin slot for a link (compact remaps visual slots only).
function promptSlot(node, graph, linkId) {
  expandOptionOutputs(node);
  const slot = originSlot(graph, linkId);
  compactOptionOutputs(node);
  return slot;
}

// 1. canonicalize: the user's legacy order (None=option_2, dress=option_3).
{
  const model = theme([opt("option_1", "bikini", ["bikini"]), opt("option_2", "None"), opt("option_3", "dress", ["dress"])], "option_2");
  const canon = canonicalizeThemeOptions(model);
  assert(canon.changed, "legacy order changes");
  assert(ids(model) === "option_1,option_2,option_3" && names(model) === "bikini,dress,None", "rows renumbered by table order, None last");
  assert(model.none_option_id === "option_3", "None gets the last id");
  assert(canon.sourceIds.join(",") === "option_1,option_3,option_2", "source ids recorded per new row");
  assert(canon.idMap.get("option_3") === "option_2" && canon.idMap.get("option_2") === "option_3", "id map swaps dress and None");
  assert(isCanonicalThemeOptions(model), "result is canonical");
  const again = canonicalizeThemeOptions(model);
  assert(!again.changed && again.sourceIds.join(",") === "option_1,option_2,option_3", "canonicalize is idempotent");
}

// 2. Manual ids and a theme without a None row are renumbered too.
{
  const model = theme([opt("anime", "Anime"), opt("real", "Real")]);
  const canon = canonicalizeThemeOptions(model);
  assert(canon.changed && ids(model) === "option_1,option_2,option_3", "manual ids become option_N; default None appended");
  assert(model.options[2].label === "None" && model.none_option_id === "option_3", "default None is last");
  assert(canon.sourceIds[2] === "none", "default None source id is the planned 'none' slot");
  const remap = planOptionIndexRemap(JSON.stringify(theme([opt("anime", "Anime"), opt("real", "Real")])), canon.sourceIds, canon.nextIds);
  assert(remap.ok && remap.identity, "positions are unchanged, so no wire moves");
}

// 3. Legacy load: links follow their option (graph.links Map, camelCase, setter outputs).
{
  const graph = makeGraph({ map: true });
  const legacy = theme([opt("option_1", "bikini", ["bikini"]), opt("option_2", "None"), opt("option_3", "dress", ["dress"])], "option_2");
  const node = themeNode(86, legacy, graph, { store: true });
  graph.addTarget(88, 4);
  addLink(graph, { id: 1, origin: 86, slot: 0, target: 88, targetSlot: 0, camel: true }); // bikini -> collect a
  addLink(graph, { id: 2, origin: 86, slot: 1, target: 88, targetSlot: 1, camel: true }); // None -> collect b
  addLink(graph, { id: 3, origin: 86, slot: 2, target: 89, targetSlot: 0, camel: true }); // dress -> child
  addLink(graph, { id: 4, origin: 86, slot: REPORT_OUTPUT_INDEX, target: 90, targetSlot: 0, camel: true }); // report
  const done = writeTheme(node, readTheme(node)); // what onConfigure does
  assert(done.ok && done.changed, "legacy document is normalized on configure");
  assert(done.applied.moved === 2 && done.applied.removed === 0, "two wires move, none removed");
  assert(done.relinked.moved === 0, "relink after remap moves nothing again");
  const model = readTheme(node);
  assert(names(model) === "bikini,dress,None" && ids(model) === "option_1,option_2,option_3", "widget is canonical");
  expandOptionOutputs(node);
  assert(originSlot(graph, 1) === 0, "bikini wire stays on slot 0");
  assert(originSlot(graph, 3) === 1, "dress wire follows dress to slot 1 (option_2)");
  assert(originSlot(graph, 2) === 2, "None wire follows None to slot 2 (option_3)");
  assert(originSlot(graph, 4) === REPORT_OUTPUT_INDEX, "report_json wire stays at 32");
  assert(node.outputs[1].s1OptionId === "option_2" && node.outputs[2].s1OptionId === "option_3", "stamps use the new ids");
  assert(node.outputs[1].label === "dress" && node.outputs[2].label === "None", "labels follow");
  compactOptionOutputs(node, "option_3");
  assert(node.outputs.map((output) => output.label || output.name).join(",") === "bikini,dress,None,report_json", "compact order = table order");
  // Idempotent: a second configure is a no-op.
  const second = writeTheme(node, readTheme(node));
  assert(second.ok && !second.changed && second.remap.identity, "second normalization is a no-op");
  assert(promptSlot(node, graph, 2) === 2 && promptSlot(node, graph, 3) === 1, "wires unchanged by the no-op");
}

// 4. Move: rows and ids swap together, wires follow (plain objects, compacted start).
{
  const graph = makeGraph();
  const doc = theme([opt("option_1", "A"), opt("option_2", "B"), opt("option_3", "C"), opt("option_4", "None")], "option_4");
  const node = themeNode(7, doc, graph);
  wire(node, graph, 0, 10, 100);
  wire(node, graph, 1, 11, 101);
  wire(node, graph, 2, 12, 102);
  wire(node, graph, 3, 13, 103);
  compactOptionOutputs(node, "option_4");
  const model = readTheme(node);
  const moved = moveThemeOption(model, "option_3", -1);
  assert(moved.ok && moved.moved, "C moves up");
  const done = writeTheme(node, model);
  const after = readTheme(node);
  assert(names(after) === "A,C,B,None" && ids(after) === "option_1,option_2,option_3,option_4", "C is now option_2, B option_3");
  assert(after.none_option_id === "option_4", "None keeps the last id");
  assert(done.applied.moved === 2, "two wires swap");
  assert(promptSlot(node, graph, 12) === 1 && promptSlot(node, graph, 11) === 2, "C and B wires follow their options");
  assert(promptSlot(node, graph, 10) === 0 && promptSlot(node, graph, 13) === 3, "A and None wires stay");
  expandOptionOutputs(node);
  assert(node.outputs[1].links.includes(12) && !node.outputs[1].links.includes(11), "plain mirror follows too");
  compactOptionOutputs(node);
  // None never moves; edges do not move.
  const fixedModel = readTheme(node);
  const noneMove = moveThemeOption(fixedModel, "option_4", -1);
  assert(!noneMove.moved, "None cannot move");
  const topMove = moveThemeOption(fixedModel, "option_1", -1);
  assert(topMove.ok && !topMove.moved, "first row cannot move up");
  const lastUser = moveThemeOption(fixedModel, "option_3", 1);
  assert(lastUser.ok && !lastUser.moved, "last user row cannot move below None");
}

// 5. Delete: later rows move up one id, their wires follow, deleted wires go.
for (const useRemoveLink of [true, false]) {
  const graph = makeGraph({ map: useRemoveLink });
  if (useRemoveLink) {
    graph.removeLink = (id) => {
      const link = graph.links.get(id);
      if (!link) return;
      const target = graph.getNodeById(link.target_id ?? link.targetId);
      const slot = link.target_slot ?? link.targetSlot;
      if (target && target.inputs[slot].link === id) target.inputs[slot].link = null;
      graph.links.delete(id);
      graph.removed.push(id);
    };
  }
  const doc = theme([opt("option_1", "A"), opt("option_2", "B"), opt("option_3", "C"), opt("option_4", "None")], "option_4");
  const node = themeNode(9, doc, graph);
  wire(node, graph, 0, 20, 200);
  wire(node, graph, 1, 21, 201);
  wire(node, graph, 1, 25, 205);
  wire(node, graph, 2, 22, 202);
  wire(node, graph, 3, 23, 203);
  wire(node, graph, REPORT_OUTPUT_INDEX, 24, 204);
  const model = readTheme(node);
  assert(deleteThemeOption(model, "option_2").ok, "delete B");
  const done = writeTheme(node, model);
  const after = readTheme(node);
  assert(names(after) === "A,C,None" && ids(after) === "option_1,option_2,option_3", "ids stay contiguous with rows");
  assert(after.none_option_id === "option_3", "None is the last id after delete");
  assert(done.remap.removed.join(",") === "1", "old slot 1 is the deleted one");
  assert(done.applied.removed === 2 && done.applied.stuck === 0, "both wires of the deleted socket are disconnected");
  assert(getLink(graph, 21) === undefined && getLink(graph, 25) === undefined, "deleted option wires are gone from graph.links");
  assert(graph.getNodeById(201).inputs[0].link === null && graph.getNodeById(205).inputs[0].link === null, "their targets are disconnected");
  if (useRemoveLink) assert(graph.removed.join(",") === "21,25", "graph.removeLink is the path used");
  assert(promptSlot(node, graph, 22) === 1, "C wire moves up to option_2");
  assert(promptSlot(node, graph, 23) === 2, "None wire moves up to option_3");
  assert(promptSlot(node, graph, 20) === 0 && promptSlot(node, graph, 24) === REPORT_OUTPUT_INDEX, "A and report wires stay");
  assert(graph.getNodeById(202).inputs[0].link === 22, "moved wire keeps its target");
  expandOptionOutputs(node);
  assert(node.outputs[3].s1OptionId === "" && node.outputs[3].hidden === true, "freed pad is unused");
  compactOptionOutputs(node);
}

// 6. Add: new row gets option_N for its row, None shifts to the last id with its wire.
{
  const graph = makeGraph();
  const doc = theme([opt("option_1", "A"), opt("option_2", "None")], "option_2");
  const node = themeNode(5, doc, graph);
  wire(node, graph, 0, 30, 300);
  wire(node, graph, 1, 31, 301);
  const model = readTheme(node);
  const added = addThemeOption(model);
  assert(added.ok && added.option.option_id === "option_3", "fresh id is not in the document");
  added.option.label = "B";
  added.option.description = "B";
  const done = writeTheme(node, model);
  const after = readTheme(node);
  assert(names(after) === "A,B,None" && ids(after) === "option_1,option_2,option_3", "new row is option_2, None option_3");
  assert(done.applied.moved === 1 && done.applied.removed === 0, "only the None wire moves");
  assert(promptSlot(node, graph, 31) === 2 && promptSlot(node, graph, 30) === 0, "None wire follows None");
}

// 7. The sanitized user fixture shape: bikini + None, then dress added the old way.
{
  const graph = makeGraph({ map: true });
  const legacy = theme([opt("option_1", "bikini", ["bikini"]), { option_id: "option_2", label: "None", description: "Not on the list" }, opt("option_3", "dress", ["dress"])]);
  const node = themeNode("87:86", legacy, graph, { store: true });
  graph.addTarget("87:88", 3);
  addLink(graph, { id: 41, origin: "87:86", slot: 0, target: "87:88", targetSlot: 0 });
  addLink(graph, { id: 42, origin: "87:86", slot: 1, target: "87:88", targetSlot: 1 });
  const done = writeTheme(node, readTheme(node));
  const after = readTheme(node);
  assert(done.changed && names(after) === "bikini,dress,None", "fixture-shaped theme normalized");
  assert(after.none_option_id === "option_3", "None-like row without none_option_id becomes option_3");
  assert(promptSlot(node, graph, 42) === 2 && promptSlot(node, graph, 41) === 0, "Collect b stays on None");
}

// 8. Invalid previous JSON: nothing is moved.
{
  const remap = planOptionIndexRemap("{", ["option_1"], ["option_1"]);
  assert(!remap.ok && remap.identity && remap.indexMap.size === 0, "invalid previous json plans no remap");
  const applied = applyOptionIndexRemap({ id: 1, outputs: [], graph: makeGraph() }, remap);
  assert(!applied.ok && applied.moved === 0, "no remap is applied");
}

// 9. An invalid draft does not touch the caller model.
{
  const model = theme([opt("option_2", "A"), opt("option_1", "B")]);
  model.select_mode = "bogus";
  const before = JSON.stringify(model);
  const planned = planThemeWrite(JSON.stringify(theme([opt("option_2", "A"), opt("option_1", "B")])), model);
  assert(!planned.ok, "invalid draft rejected");
  assert(JSON.stringify(model) === before, "caller model untouched on reject");
}

// 10. Display order and canonical array agree.
{
  const model = theme([opt("option_4", "X"), opt("none", "None"), opt("option_2", "Y")], "none");
  const display = optionDisplayOrder(model.options, model.none_option_id).map((option) => option.label).join(",");
  canonicalizeThemeOptions(model);
  assert(names(model) === display && display === "X,Y,None", "canonical array is the table order");
}

console.log(`ok ${checks}`);
