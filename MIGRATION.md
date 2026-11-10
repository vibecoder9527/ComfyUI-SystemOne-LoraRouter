# Migration

Positive is the input above negative. Positive is required. Negative is optional; unconnected or blank is sent as empty. This break removes `run`, `enable_json`, `theme_result`, and `S1_THEME_RESULT`. API widgets move to **SystemOne Settings** (`S1Settings`). Theme Root (`S1ThemeRoot`) always decides. A downstream Theme (`S1Theme`) takes one parent option slot on `upstream`. Outputs are `S1_DECISION` option slots, not one `theme_result`.

`schema/migrate.py` rewrites JSON. It does not register nodes and it does not call SystemOne.

`S1ThemeCollect` stays. It now merges two `S1_DECISION` payloads. It is not removed. Option-slot branching replaces enable trees. Collect is the fan-in. `a` and `b` are both optional. One wired branch is returned unchanged. An `ExecutionBlocker` or missing optional input is ignored. Zero usable inputs raises `SchemaError`.

## What a 51f1904 workflow loses

| Removed | Replacement |
| --- | --- |
| Theme `api_key`, `api_model`, `endpoint`, `noul_threshold`, `on_error`, `min_confidence` | One `S1Settings` node, wired into `settings` |
| `positive` / `negative` widgets | `STRING` sockets. Positive is required and is the input above negative. Negative is optional. Not stored in `theme_json` |
| `run=enabled` | `S1ThemeRoot`. It always decides. Leftover `enable_json` clauses are ignored |
| `run=when_upstream` plus `enable_json` | `S1Theme` plus one wire from the parent option slot into `upstream` |
| `run=disabled` | The node is dropped. Nothing is left on the canvas for it |
| `theme_result` / `S1_THEME_RESULT` | The option slot whose `option_id` you care about, type `S1_DECISION` |
| `enable_json` on the node | Gone. `parse_enable_rules` remains for the helper only |
| Output 0 as the whole theme result | Output 0 is option 0. Do not keep the old link |

`none_option_id` is unchanged: that option contributes no tags when it is chosen, and its slot still emits.

`migrate_router_graph` reads a ComfyUI API prompt (`id -> {class_type, inputs}`) or `{"nodes": [ ... ]}` with flat widget fields. It returns a plan: `settings_nodes`, `nodes`, `wires`, `dropped`, `warnings`, `removed`, and `limits`. It is not a workflow you can queue unchanged. Positive and negative are copied as text so you can paste them onto prompt nodes, positive first. The API key is copied onto the settings inputs and is not repeated in warnings.

```python
import json
from schema.migrate import migrate_router_graph

plan = migrate_router_graph(json.load(open("my_51f1904_prompt.json", encoding="utf-8")))
print(plan["removed"])
for node in plan["settings_nodes"]:
    print(node["id"], node["inputs"]["endpoint"], node["inputs"]["on_error"])
for wire in plan["wires"]:
    print(wire)
```

Rules for that plan:

- Themes that share the same six API fields share one `S1Settings` node (`settings`, then `settings_2`, …). A dropped theme does not create a settings node.
- `run=enabled` becomes `S1ThemeRoot`. If `enable_json` had clauses, the warning says `enable_json` is ignored.
- `run=when_upstream` becomes `S1Theme`. One clause whose op is `eq` or `includes_any` and whose `option_ids` has exactly one id becomes `upstream: [parent_id, option_index]` when that option exists on the parent's `theme_json` and the clause's `theme_id` matches the parent. The old link `[parent, 0]` was `theme_result`, not "option 0", and it is not reused as a slot index by itself.
- Several clauses, `includes_any` with more than one id, `includes_all`, `neq`, `skipped`, and `answered` do not become one wire. The warning tells you to place one Theme copy per option, or to wire the slot yourself. A downstream theme has one `upstream` socket.
- `run=disabled` or an unknown `run` drops the node.
- LoRA Aggregate's `theme_result` input is removed. The warning says output 0 is no longer the whole theme result and that you should connect `decision` to the option slot. The helper does not guess which slot.
- Theme Collect links that used to come from an `S1Theme` `theme_result` are cleared, with a warning to retarget them at an option slot.
- `limits.max_option_outputs` is 32. `limits.report_output_index` is 32.

`removed` from `migrate_router_graph` names `run`, `enable_json`, `theme_result`, `S1_THEME_RESULT`, and each old Theme API widget.

Active wiring sketch: `examples/wiring.art_and_character.json`. Old enable documents are parked in `examples/legacy/enable.empty.json` and `examples/legacy/enable.when_anime.json`.

## Older library and sequence documents

`S1ThemeLibrary` and `S1ThemeSequence` are still not registered. The runtime parsers reject `lora_bindings`, `fallback_option_id`, and a `themes` list. There is no compatibility mode that executes a sequence.

| Old | New |
| --- | --- |
| `S1ThemeLibrary` / `S1_THEME_LIB` | One Theme Root or Theme per theme. `theme_json` is one theme object |
| `S1ThemeSequence` / `sequence_json` | `plan_sequence` chooses `S1ThemeRoot` or `S1Theme`. Wiring an option slot replaces `enable_step` |
| Option `lora_bindings` | Option `tags`. LoRA Aggregate matches tags on `S1LoraLibrary` entries |
| Per-binding strengths | Dropped. Aggregate uses the library strengths and applies each `lora_id` once |
| `strength_conflict` | Removed. One library strength, one apply |
| `fallback_option_id` | Removed. A low-confidence choice is kept. `none_option_id` still means "this option contributes no tags" |
| `rewrite_options`, `rewrite_instructions`, `set_select_mode` | Not migrated. `plan_sequence` warns |
| `disable_step` | The node is omitted. A theme does not turn off conditionally |
| Sidebar tab **S1 Editors** | Removed. **Open visual editor** opens a modal on the node. There is no Apply to node button |

```python
import json
from schema.migrate import migrate_theme_library, plan_sequence, retag_lora_library

library = json.load(open("examples/legacy/theme_library.minimal.json", encoding="utf-8"))
migrated = migrate_theme_library(library)
for item in migrated:
    print(item.notes)
    print(json.dumps(item.document, ensure_ascii=False, indent=2))

lora = json.load(open("examples/lora_library.minimal.json", encoding="utf-8"))
updated, notes = retag_lora_library(lora, [item.document for item in migrated])

plan = plan_sequence(open("examples/legacy/sequence.minimal.json", encoding="utf-8").read())
for node in plan["nodes"]:
    print(node["theme_id"], node["class_type"], node["upstream_wire"], node["dropped"])
```

`plan_sequence` is advisory.

- `enabled_by_default: true` and no `disable_step` becomes `class_type: S1ThemeRoot`. Enable clauses are not wires on a root. The plan warns that they are ignored.
- A step that starts disabled and has one `enable_step` action that names a single option becomes `class_type: S1Theme` with `upstream_wire` `{theme_id, option_id, op}`. The clause's `theme_id` is the referenced step's `theme_id`, not the old `step_id`.
- Several options, several clauses, or an op that is not `eq` / `includes_any` of one id do not become one wire. The warning says so. `upstream_wire` is null.
- A step that cannot become a root or a single option wire is `dropped`, with `class_type: null`. That includes `disable_step` and a step that started disabled with no `enable_step`.
- `rewrite_*` actions are warnings.
- The same `theme_id` on more than one step is a warning. The editor assigns a free `theme_N` when you add or duplicate a theme node and leaves a unique saved id in place. Two restored nodes that already share an id are reported and not rewritten. A decision chain still rejects a repeated theme_id.
- `removed` names `S1ThemeLibrary`, `S1ThemeSequence`, `lora_bindings`, `fallback_option_id`, `strength_conflict`, `sequence_json`, `run`, `enable_json`, `theme_result`, and `S1_THEME_RESULT`.

For `examples/legacy/sequence.minimal.json` the plan is: art style is Theme Root, character pack is Theme with `includes_any` / `anime` on theme `art_style`. The `rewrite_instructions` and `rewrite_options` actions are warnings. The character theme in `examples/theme.character_pack.json` still lists both `waifu_a` and `waifu_b`. Delete `waifu_b` yourself if you still want it gone.

Library migration rules are unchanged: bindings become tags when the option had no tags; existing tags win; binding strengths are dropped; blank ids are filled; `parse_theme` still has to accept the result.

`retag_lora_library` appends a tag onto a library entry when an option tag equals that entry's `lora_id` and the tag is not already there. The active minimal library already uses descriptive tags (`style_anime`, not `style_anime_v3`). Set those on the entries, as in `examples/lora_library.minimal.json`.

## Checks after you rewire

- Settings is connected to every Theme Root and Theme that should call SystemOne.
- Positive is the input above negative on each theme. Positive is required. Negative is optional. Prompts are not inside `theme_json`.
- The child Theme's `upstream` comes from the parent option slot, not from output 0 of an old theme and not from `report_json` (index 32).
- Aggregate's `decision` comes from a slot you expect to emit, or from Theme Collect of one or more branches.
- You did not leave a second copy of the API widgets on the theme.
- A theme id is unique along any chain you will queue. `none_option_id` is still an option of that theme when you set it.

## Frontend 1.57 link preservation

ComfyUI 0.44 with frontend 1.57.6 keeps option wires in `graph.links`. `output.links` can be empty, and assigning it disconnects the link. Setting `output.hidden` on a *connected* socket drops wires, including a wire from an option slot into Theme Collect. Unused pads with no live wire are hidden and labeled `·`. A connected socket is never hidden. The first sync after a load stamps `s1OptionId` and does not move or delete an existing wire. A later sync moves a wire only when its option id is still in `theme_json`. A wire that is still connected is kept when that id is gone. A default 以上皆非 option is ensured at edit/run time. A saved None-like option (for example label `None` / description `Not on the list`) is reused so Collect links on slots 0 and 1 stay put. Theme Collect still runs when only some of its optional sockets carry a real `S1_DECISION`. Connecting a slot offers another empty input.
