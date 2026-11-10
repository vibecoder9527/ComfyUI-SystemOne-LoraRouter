# SystemOne LoRA Router

This file is the contract for the custom node. Positive is the input above negative. Positive is required. Negative is optional; unconnected or blank is sent as empty. Prompts are input sockets. They are not fields of `theme_json`.

| Class | Display name | Output |
| --- | --- | --- |
| `S1LoraLibrary` | LoRA Library | `S1_LORA_LIB` |
| `S1Settings` | SystemOne Settings | `S1_SETTINGS` |
| `S1ThemeRoot` | Theme Root | 32 × `S1_DECISION`, then `STRING` (`report_json` at index 32) |
| `S1Theme` | Theme | 32 × `S1_DECISION`, then `STRING` (`report_json` at index 32) |
| `S1ThemeCollect` | Theme Collect | `S1_DECISION` |
| `S1LoraAggregate` | LoRA Aggregate | `MODEL`, `CLIP`, `STRING` (`report_json`) |

`S1ThemeLibrary`, `S1ThemeSequence`, `S1_THEME_LIB`, and `S1_THEME_SEQ` are not registered. `theme_result` and `S1_THEME_RESULT` are not socket types. `run` and `enable_json` are not widgets.

Custom type names are strings. ComfyUI matches them as strings. Custom inputs set `forceInput`.

## Wiring

```
SystemOne Settings ──S1_SETTINGS──► Theme Root
                                └──► Theme

positive ──► Theme Root.positive
negative ──► Theme Root.negative

Theme Root option slot (anime) ──S1_DECISION──► Theme.upstream
Theme option slot ──S1_DECISION──► LoRA Aggregate.decision

LoRA Library ──S1_LORA_LIB──► LoRA Aggregate
MODEL ──────────────────────► LoRA Aggregate
CLIP (optional) ────────────► LoRA Aggregate
```

Theme Root has no `upstream` input. It always decides when settings and `theme_json` are valid. A downstream Theme takes one `S1_DECISION` on `upstream`. That wire replaces `enable_json`. The parent slot that fired is the only parent this theme sees.

Each selected option slot carries the accumulated decisions and tags, including upstream themes. Several selected slots of one multi theme share that same result. Wire any one of them into Aggregate or into a child Theme.

`none_option_id`, when selected, still emits on its slot and contributes no tags. A child wired to that slot runs.

## SystemOne Settings

`S1Settings` widgets, in order: `api_key`, `api_model`, `endpoint` (default `https://system-one.dev/v1/systemone`), `noul_threshold` (default `0.5`), `on_error` (`passthrough` | `raise`, default `passthrough`), `min_confidence` (default `0.0`).

The node does not call SystemOne. It returns one frozen settings object. Theme Root and Theme take that object on `settings`. They have no API widgets.

The API key is the widget when it is non-empty, otherwise `SYSTEM_ONE_API_KEY`. The key is never written into `report_json`. `repr` of the settings object says `api_key=set` or `api_key=empty`. A blank `api_model` is sent as `unspecified`. A blank endpoint uses the default. `on_error` and the unit-interval fields are checked when the settings node runs and again when a theme runs.

LoRA Aggregate has its own `on_error`. That one is weight loading, not the theme's SystemOne policy.

## Theme inputs

Theme Root, in order:

1. `positive` (`STRING`, `forceInput`, required)
2. `negative` (`STRING`, `forceInput`, optional, the socket under positive)
3. `settings` (`S1_SETTINGS`, `forceInput`)
4. `theme_json`

Theme adds `upstream` (`S1_DECISION`, `forceInput`) before `theme_json`. Negative stays optional on Theme as well.

Positive is the input above negative. Positive is required. Negative is optional; unconnected or blank is sent as `""`. Each theme has its own prompts. They are not copied from the parent. The request state is `{ "positive": <positive>, "negative": <negative> }`. Prompts are not stored in `theme_json`.

There is no `run` widget. There is no `enable_json` widget.

## Option slots

`RETURN_TYPES` is 32 times `S1_DECISION` plus one `STRING`. `RETURN_NAMES` are `option_1` … `option_32` and `report_json`. Slot `i` is `theme.options[i]`. Slots past the option list are blockers. The report stays at index 32.

A theme with more than 32 options raises `SchemaError` on the node before any HTTP call. The engine can still batch noul questions of 32 when `run_theme` is called directly with a larger document. The node is the cap users hit.

| Slot | When it emits |
| --- | --- |
| Selected option, status `ok` | `S1_DECISION` with `emitted_reason=selected`. All selected slots share one accumulated result. |
| `none_option_id` selected | Emits, and `_contribute` adds no tags from that option. |
| Unselected option | `ExecutionBlocker` with `message is None`. |
| This theme's decision is `error` (`on_error=passthrough`) | The accumulated payload on every real option slot, `emitted_reason=passthrough_error`. |
| No options, or a multi theme that selected nothing | Every slot is a blocker. Upstream tags stay on the result and are not placed on a slot. |
| `upstream` is already an `ExecutionBlocker` | Every slot of this downstream node is a blocker. `theme_json` is not parsed. SystemOne is not called. |

ComfyUI does not execute a node when a required input is `comfy_execution.graph_utils.ExecutionBlocker`. The blocker then propagates. This package imports that class when it can. Otherwise it returns `LocalExecutionBlocker` with the same `message`. Unittest sees the stand-in. A live skip happens only when the returned object is ComfyUI's class.

`report_json` lists `slots` as `{option_id, emitted}` for real options. `emitted` is `selected`, `blocked`, or `passthrough_error`. The report does not contain the API key. `api.key_source` is `widget`, `env`, or `missing`. `api.called` is false when nothing was sent, including a single remaining option and a theme with no options.

### Passthrough is wider than an old enable rule

`on_error=passthrough` emits on every real option slot so Aggregate can still see upstream tags. A child Theme wired to any of those slots also runs. That is not the old "this theme failed, so dependents stay off" behavior.

`on_error=raise` raises `ThemeError`. The exception has `.result` and `.report`.

Invalid `theme_json`, a settings object that is not `S1_SETTINGS`, a downstream `upstream` that is not `S1_DECISION` and not a blocker, or a duplicate `theme_id` already in the upstream result raises `SchemaError`. No HTTP call is made. `on_error` does not catch `SchemaError`.

## Decision

`select_mode: single` sends one SystemOne `choice` question. The question id is the `theme_id`. Criteria map each `option_id` to that option's `description`. If only one option remains, the runner selects it and does not call the API. It does not invent `__none__`. A single theme with at least one option selects exactly one option on success.

`select_mode: multi` sends one `noul` question per option. The question id is `{theme_id}__{option_id}`. A score greater than or equal to `noul_threshold` selects the option. Inside the engine, more than 32 noul questions are split across requests that share the same state. The node never reaches that path: it rejects the document first.

An invalid choice fails the decision. When `confidence` is present and below `min_confidence`, the choice is kept and the report notes `low_confidence_kept`. There is no fallback option. A confidence equal to `min_confidence` is not marked. A missing confidence is not marked.

Tags from an `ok` decision are the first-seen union of the contributing options' tags, skipping `none_option_id`. The accumulated result keeps the first-seen union of tags from `ok` decisions only.

## Theme JSON

One theme object. A `{ "themes": [...] }` library is rejected.

```json
{
  "version": 1,
  "theme_id": "art_style",
  "title": "畫風",
  "instructions": "判斷提示詞的主要畫風。",
  "select_mode": "single",
  "none_option_id": "none",
  "options": [
    { "option_id": "anime", "label": "動漫", "description": "…", "tags": ["style_anime"] }
  ]
}
```

- `version` defaults to 1 and must be 1 when present.
- `theme_id`, `title`, and `instructions` are required. Ids contain no whitespace.
- `select_mode` is `single` or `multi`.
- `options` may be empty in the stored document. A theme with no options is a decision error, does not call the API, and has no slot that emits.
- Each option has `option_id`, `label`, `description`, and optional `tags` (exact strings). Option order is output-slot order.
- `none_option_id`, when set, names an option of this theme. If that option is selected it contributes no tags. Other selected options in `multi` still contribute their tags.
- `lora_bindings` is rejected at parse time. Selected options contribute tags. See MIGRATION.
- `fallback_option_id` is rejected and is not applied.

`parse_theme` does not assign ids. The editor fills a blank id on one document with `theme_1` and blank option ids with `option_N`. Ids across theme nodes come from `planThemeIds`, which runs when a theme node is added, after a workflow is configured, and again inside `queuePrompt` / `graphToPrompt`. The modal shows that stored id on a read-only line.

- A new or duplicated node keeps a non-empty id that is still free, and otherwise takes the lowest free `theme_N`. Restored non-empty ids are reserved first.
- Two restored nodes with the same non-empty id are a conflict. Theme JSON is left unchanged. The node title gains ` (theme_id conflict)`. A decision chain still rejects a repeated theme_id.
- Re-running the planner on a graph that is already unique changes nothing.
- Each graph is numbered on its own (`app.graph`, and each nested `node.subgraph`).

`enable_json` is not part of the theme document anymore. `parse_enable_rules` remains so `migrate_router_graph` and `plan_sequence` can read old clauses. The runtime does not match those clauses. Old examples live in `examples/legacy/`, including `enable.empty.json` and `enable.when_anime.json`.

## Theme Collect

Inputs start as optional `a` and `b` so existing workflows keep their links, then more optional sockets appear as branches are connected (up to 16). The output is one `S1_DECISION` named `decision`. One wired branch is returned unchanged (`emitted_reason` stays whatever that slot emitted). Two real payloads merge with `emitted_reason=collected`. An `ExecutionBlocker` or missing optional input is ignored so a selected sibling can stay linked and Collect can run. ComfyUI 0.44 skips a node when any input is an `ExecutionBlocker`, including optional sockets; this pack sanitizes Collect's optional blockers before that short-circuit so `merge` can run. A mixed optional batch keeps live items in place and skips only the blocked slices. The opt-in flag is not inherited by a subclass unless that class declares it. Zero usable inputs raises `SchemaError`. Order is the first copy of each `theme_id`: every decision from `a`, then decisions from `b` whose id is not already kept. An identical later decision is dropped, so a shared ancestor is stored once and its tags are not doubled. Identical means status, enabled, selected ids, tags, select mode, option tag contributions, error, reason, and `raw` all match. A difference raises `SchemaError`.

Collect has no `on_error`. It does not have 32 option slots.

Chain Collect nodes to merge more than two payloads.

## LoRA library

```json
{
  "version": 1,
  "loras": [
    {
      "lora_id": "style_anime_v3",
      "name": "anime_style_v3.safetensors",
      "strength_model": 0.8,
      "strength_clip": 0.8,
      "tags": ["style_anime"],
      "enabled_default": true
    }
  ]
}
```

`name` is the file name under ComfyUI `loras/`. The library node does not open the file. `enabled_default` defaults to true (always-on). Uncheck it to make the entry tag-gated. Example libraries set `enabled_default: false` so demos stay tag-driven. `tags` defaults to an empty list. Stored JSON has `strength_model` and `strength_clip`. It has no `strength` key. The editor writes one number into both strength fields. Existing documents whose strengths differ still parse and apply as stored.

Ids: the smallest unused `lora_N` starting at `lora_1`, filling gaps. A non-empty id is kept. `parse_lora_library` does not assign ids.

See `examples/lora_library.empty.json` and `examples/lora_library.minimal.json`.

## LoRA Aggregate

Inputs: `model` (`MODEL`), `lora_lib` (`S1_LORA_LIB`), `decision` (`S1_DECISION`). Optional: `clip` (`CLIP`), `on_error` (`passthrough` | `raise`, default `passthrough`).

`decision` is a selected option slot or the output of Theme Collect. A raw theme result from before this break is not accepted.

`enabled_default: true` (always-on) always matches, even with no tag overlap. `enabled_default: false` (tag-gated) matches only when any of its tags is in the payload's tag list. Comparison is exact and case-sensitive. Tag-gated entries with no overlap are omitted (not listed in `skipped`).

Each matching `lora_id` is applied once, in `lora_id` order, through `apply_loras`, using the library strengths only. There is no per-option strength and no `strength_conflict` policy.

Theme errors already stored on the decision are copied into the aggregate report. They do not make Aggregate raise. Matching still uses the tags the decision kept.

`on_error` here is forwarded to `apply_loras` only:

- Outside ComfyUI, weights are not patched. Aggregate leaves MODEL and CLIP unchanged, records a note, and does not raise.
- Inside ComfyUI, a missing or failing file is skipped on `passthrough` and recorded in `errors`. `raise` raises `ApplyError`.
- A `SchemaError` (the wires are not a library and an `S1_DECISION`) is not an apply failure. `passthrough` returns the input MODEL and CLIP. `raise` propagates `SchemaError`.

## Editor

`js/` is a ComfyUI frontend extension (`WEB_DIRECTORY`). The extension name is `SystemOne.LoraRouter.UI`. It does not register a sidebar tab. The sidebar tab from the previous package is gone.

LoRA Library, Theme Root, and Theme grow an **Open visual editor** button (`serialize: false`). The same item is on the node right-click menu. It opens a modal. SystemOne Settings, Theme Collect, and LoRA Aggregate have no editor button.

The modal edits `library_json` or `theme_json`. Valid edits are written after about 220ms. While the modal is visible, a 500ms poll reloads the form when that JSON widget changed outside the form. There is no Apply to node button and no Reload from node button. Invalid fields use the CSS class `s1-invalid`. An invalid draft is not written, and option sockets are left as they were.

`lora_id`, `theme_id`, and `option_id` are assigned automatically and shown in titles, not as form fields. Each theme has a default 以上皆非 option with its own output slot; a saved None-like option is reused. Option tags offer values already present on LoRA Library and Theme nodes in the graph. The LoRA Library form uses compact rows (enabled_default toggle, name, strength, tags). One strength field is labeled `strength (model & clip)`. Positive is the input above negative on the nodes, not in this modal. The LoRA name field can pick a file from the ComfyUI loras list. A typed name that is not in the list is still stored.

`planOptionOutputs` builds 32 slots from `theme_json`. Slots that have an option are named `label (option_id)`, or the id when the label is blank. Unused pads are marked in the plan only. `syncOptionOutputs` runs after a successful theme write and after `reconcileThemeIds`. It does not call reconcile back. The first sync, when no output has `s1OptionId`, stamps ids by index and does not move links. A `report_json` name alone does not count as a prior sync. A later sync moves `graph.links` `origin_slot` / `originSlot` to the option's new index. A wire whose previous id is empty stays put so that stamp can claim it. A wire whose option id disappeared stays connected. Deleting it is not required, and rewriting `output.links` disconnects it on frontend 1.57.6. A live wire is one whose id is in `output.links` or whose `graph.links` entry has `origin_id` / `originId` equal to the node and `origin_slot` / `originSlot` equal to the socket. Unused pads with no live wire set `output.hidden` true so only defined options show. A connected socket stays visible (`output.hidden` false). Frontend 1.57.6 (ComfyUI 0.44) drops a wire when a connected socket is hidden, and it keeps the link record in `graph.links` when `output.links` is empty. Report links at index 32 stay put. `orderThemePromptInputs` keeps the negative socket immediately under positive after ComfyUI lists optional inputs last.

## Migration

`schema/migrate.py` is offline: `migrate_theme_library`, `migrate_theme_document`, `retag_lora_library`, `plan_sequence`, and `migrate_router_graph`. See [MIGRATION.md](MIGRATION.md). `examples/wiring.art_and_character.json` is the active wiring sketch. Old enable documents are in `examples/legacy/`.

## Known limitations

- Execution skip of an unselected slot is real only when ComfyUI's `ExecutionBlocker` is what the node returned. The local stand-in does not, by itself, stop a caller that ignores it. Downstream `decide` does notice a blocker and refuses to call SystemOne if something invokes it anyway.
- Unused option sockets with no live wire are hidden. Connected sockets are never hidden. On ComfyUI 0.44 / frontend 1.57.6, hiding a connected socket drops its wire, and `output.links` is not the link store. Extra sockets still return blockers.
- The first option-slot sync does not retarget a legacy `theme_result` link. Output 0 of a 51f1904 theme was the whole result, not option 0.
- `on_error=passthrough` emits on every option slot.
- A multi theme that selects nothing does not emit upstream tags. A theme with no options does not either.
- Theme Collect ignores a blocked or missing optional input and keeps the other decision. Two real payloads still merge. Zero usable inputs raises `SchemaError`. That behavior also requires the load-time wrapper around ComfyUI 0.44 `_async_map_node_over_list`. If the wrapper cannot be installed, a `ThemeCollectHookWarning` is emitted and Collect stays fail-closed. The hook is applied at most once. If a later wrapper replaces the map function, hides `__wrapped__`, and clears the module mark, a second install cannot be reliably detected and is documented as a limitation; the usual displacement case warns and does not stack.
- The modal polls while it is visible. It does not subscribe to widget changes.
- Restored duplicate theme ids are reported and left unchanged.
- Tag match is exact any-overlap.
- `apply_loras` does not patch weights outside ComfyUI.
- Invalid theme JSON fails the theme node even when `on_error` is `passthrough`.
