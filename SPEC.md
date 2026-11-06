# SystemOne LoRA Router

This file is the contract for the custom node. The previous SPEC was a Traditional Chinese draft of a three-node theme library and theme sequence. That draft is retired. This revision is English and describes the nodes that are registered now.

Four canvas nodes. A theme decides tags. LoRA Aggregate matches those tags to a LoRA library and applies each matched LoRA once.

| Class | Display name | Output |
| --- | --- | --- |
| `S1LoraLibrary` | LoRA Library | `S1_LORA_LIB` |
| `S1Theme` | Theme | `S1_THEME_RESULT`, `STRING` (`report_json`) |
| `S1ThemeCollect` | Theme Collect | `S1_THEME_RESULT` |
| `S1LoraAggregate` | LoRA Aggregate | `MODEL`, `CLIP`, `STRING` (`report_json`) |

`S1ThemeLibrary`, `S1ThemeSequence`, `S1_THEME_LIB`, and `S1_THEME_SEQ` are not registered.

Custom type names are strings. ComfyUI matches them as strings. Custom inputs set `forceInput`.

## Wiring

Use one accumulated chain for a decision tree:

```
LoRA Library ──S1_LORA_LIB──┐
                            ├─► LoRA Aggregate ──MODEL / CLIP / report_json
MODEL ──────────────────────┘
CLIP (optional) ────────────┘

Theme (run=enabled) ──S1_THEME_RESULT──► Theme (run=when_upstream) ──► LoRA Aggregate
```

Each Theme output already contains every upstream decision plus its own. Wire the last Theme into LoRA Aggregate. A downstream theme reads that accumulated result. It does not see themes that are not on its upstream wire.

`run=when_upstream` targets option ids on an upstream `theme_id`. That is how a selected option turns a later theme on. An unconditional boolean is not required.

A root that should always decide sets `run` to `enabled`. Every theme defaults to `disabled`. A disabled theme does not call SystemOne and does not add tags. It still appends a `skipped` decision, so a later theme can target it with `op: skipped`.

Theme Collect merges two `S1_THEME_RESULT` values. Order is the first copy of each `theme_id`: every decision from input `a`, then decisions from input `b` whose id is not already kept. An identical later decision is dropped, so a shared ancestor is stored once and its tags are not doubled. Identical means status, enabled, selected ids, tags, select mode, option tag contributions, error, reason, and `raw` all match. A difference raises `SchemaError`. Collect has no `on_error`. Error strings already recorded are kept in first-seen order, without repeating the same string. Chain Collect nodes to merge more than two results.

A fan-out that meets again is supported when the shared decisions match:

```
A (enabled) ──► B (when_upstream) ──► Theme Collect ──► Aggregate
           └──► C (when_upstream) ──┘
```

Collect(B, C) yields A once, then B, then C, when B is input `a` and C is input `b`. A chain without Collect is still valid:

```
A (enabled) ──► B (when_upstream, clauses target A's options) ──► C (when_upstream) ──► Aggregate
```

B runs only when A's selection matches. C still sees A's selection and B's skip or answer, because both decisions are in the result C receives. One Theme node still raises `SchemaError` before any HTTP call when its own `theme_id` is already in its upstream result. That is a second run of the same theme, not a merge of two snapshots.

## Theme node

Required widgets, in order:

1. `positive` (multiline string)
2. `negative` (multiline string, directly under positive, default `""`)
3. `theme_json`
4. `run`: `disabled` | `enabled` | `when_upstream`. Default `disabled`.
5. `enable_json` (always present and always validated)
6. `api_key`
7. `api_model`

Optional: `upstream` (`S1_THEME_RESULT`), `endpoint` (default `https://system-one.dev/v1/systemone`), `noul_threshold` (default `0.5`), `on_error` (`passthrough` | `raise`, default `passthrough`), `min_confidence` (default `0.0`).

Prompts are per theme. They are not inherited. The request state is `{ "positive": <positive>, "negative": <negative> }`. A blank negative is `""`. Prompts are not stored inside `theme_json`.

The API key is the `api_key` widget when it is non-empty, otherwise the `SYSTEM_ONE_API_KEY` environment variable. The key is never written into `report_json`. A blank `api_model` is sent as `unspecified`.

### Run

| `run` | Behavior |
| --- | --- |
| `disabled` | Do not call SystemOne. Add no tags. Append a skipped decision with reason `disabled`. |
| `enabled` | Always decide. `enable_json` is parsed and ignored. This is the explicit root switch. |
| `when_upstream` | Decide only when `enable_json` matches the upstream result. No upstream, or an empty clause list, does not enable the theme. Reason when unmatched: `enable_rules_unmatched`. |

`match` is `any` (OR, the default) or `all` (AND). A clause whose `theme_id` is absent from the upstream result is false.

| `op` | Match |
| --- | --- |
| `eq` | That theme's status is `ok` and its selected set equals this one option id. |
| `neq` | That theme's status is `ok` and its selected set is not this one option id. A skip or an error does not match. |
| `includes_any` | Status is `ok` and the selection intersects the option ids. |
| `includes_all` | Status is `ok` and the selection contains every option id. |
| `skipped` | Status is `skipped`. No option ids. |
| `answered` | Status is `ok`. No option ids. |

Option ops require exactly one option id for `eq` and `neq`, and at least one for `includes_any` and `includes_all`. Nested chains are deterministic: a theme only evaluates decisions already stored on the upstream result.

### Theme JSON

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
- `options` may be empty in the stored document. An enabled theme with no options is a decision error and does not call the API.
- Each option has `option_id`, `label`, `description`, and optional `tags` (exact strings). Labels and descriptions may be empty.
- `none_option_id`, when set, names an option of this theme. If that option is selected it contributes no tags, even when the option lists tags. Other selected options in `multi` still contribute their tags. `none` stays a real option id, so a downstream clause can target it.
- `lora_bindings` is rejected. Selected options contribute tags.
- `fallback_option_id` is rejected and is not applied.

`parse_theme` does not assign ids. `assignThemeDocument` fills a blank id on one document with `theme_1` and blank option ids with `option_N`, and it keeps any non-empty id. Ids across Theme nodes come from `planThemeIds`, which runs when a Theme is added, after a workflow is configured, and again inside `queuePrompt` / `graphToPrompt` before widget values are copied into the prompt. The modal shows that stored id on a read-only line.

- A new or duplicated node keeps a non-empty id that is still free, and otherwise takes the lowest free `theme_N`. Restored non-empty ids are reserved first, so a new `theme_1` does not displace a saved `theme_1`. Enable JSON is not rewritten.
- A restored node keeps a non-empty id that no other restored node uses, including manual ids and `theme_2`. A blank restored id is filled with the next free `theme_N`, because no enable rule could have named an empty id.
- Two restored nodes with the same non-empty id are a conflict. Neither theme JSON nor enable JSON is rewritten. The node title gains ` (theme_id conflict)` and the modal shows which id and which nodes. Queueing them in one result still raises `SchemaError`.
- Among ordinary new nodes that share an id, the earlier node in the graph keeps it. Re-running the planner on a graph that is already unique changes nothing.
- Each graph is numbered on its own. The walk is `app.graph` and each nested `node.subgraph`. The same `theme_1` in two subgraphs is not a conflict. The walk does not see a workflow that is not loaded. An API client that submits saved JSON without the extension uses the ids in that JSON.
- A duplicate is numbered after LiteGraph copies widget values: on a timer after `nodeCreated`, again from `theme_json`'s `serializeValue`, and again inside `queuePrompt` / `graphToPrompt` when those methods exist. `nodeCreated` itself runs before that copy, and during workflow configure it does not number, because saved widget values are applied after that hook.

### Decision

`select_mode: single` sends one SystemOne `choice` question. The question id is the `theme_id`. Criteria map each `option_id` to that option's `description`. If only one option remains, the runner selects it and does not call the API. It does not invent `__none__`.

`select_mode: multi` sends one `noul` question per option. The question id is `{theme_id}__{option_id}`. The instruction is the theme instructions, then `具體選項：{label} — {description}`, then `是否應啟用此選項？`, with the true criterion `提示詞明確需要或強烈暗示此選項` and the false criterion `提示詞不需要此選項`. A score greater than or equal to `noul_threshold` selects the option. More than 32 options are split across requests that share the same state. The batch size is 32.

An invalid choice fails the decision. When `confidence` is present and below `min_confidence`, the choice is kept and the report notes `low_confidence_kept`. There is no fallback option. A confidence equal to `min_confidence` is not marked. A missing confidence is not marked.

Tags from an `ok` decision are the first-seen union of the contributing options' tags, skipping `none_option_id`. The accumulated result keeps the first-seen union of tags from `ok` decisions only.

### Errors

Invalid `theme_json`, invalid `enable_json`, a bad `run` or `on_error`, a bad endpoint, a bad upstream type, or a duplicate `theme_id` raises `SchemaError`. The theme node does not catch it. The graph fails. No HTTP call is made. This differs from the old sequence node, which could passthrough a bad sequence document.

API failures, an invalid choice, and other decision failures use `on_error`:

- `raise`: raise `ThemeError`. The exception has `.result` and `.report`.
- `passthrough` (default): append a decision with `status=error` and `enabled=true`, add no tags, keep upstream tags, and add the note `on_error=passthrough: this theme added no tags.`

`report_json` includes `api.called`. It is false when the theme is skipped, when an enabled theme has no options, or when a single remaining option skips the API. It is true when HTTP was attempted, including a failed call. `api.key_source` is `widget`, `env`, or `missing`. The report does not contain the key.

## Enable JSON

```json
{
  "version": 1,
  "match": "any",
  "clauses": [
    { "theme_id": "art_style", "op": "includes_any", "option_ids": ["anime"] }
  ]
}
```

An empty clause list is valid and matches nothing. See `examples/enable.when_anime.json` and `examples/enable.empty.json`.

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

`name` is the file name under ComfyUI `loras/`. The library node does not open the file. `enabled_default` defaults to true. `tags` defaults to an empty list. Stored JSON has `strength_model` and `strength_clip`. It has no `strength` key. The editor writes one number into both strength fields. Existing documents whose strengths differ still parse and apply as stored.

Ids: the smallest unused `lora_N` starting at `lora_1`, filling gaps. A non-empty id is kept, including manual ids such as `style_anime_v3`. Blank means missing, `null`, `""`, or whitespace. `parse_lora_library` does not assign ids.

The empty library `{ "loras": [] }` is valid. See `examples/lora_library.empty.json` and `examples/lora_library.minimal.json`.

## LoRA Aggregate

Inputs: `model` (`MODEL`), `lora_lib` (`S1_LORA_LIB`), `theme_result` (`S1_THEME_RESULT`). Optional: `clip` (`CLIP`), `on_error` (`passthrough` | `raise`, default `passthrough`).

A library entry matches when `enabled_default` is true and any of its tags is in the result's tag list. Comparison is exact and case-sensitive. Entries with no overlapping tag are omitted. An entry that overlaps but has `enabled_default: false` is listed in `skipped` with reason `enabled_default is false` and is not applied.

Each matching `lora_id` is applied once, in `lora_id` order, through `apply_loras`, using the library strengths only. There is no per-option strength and no `strength_conflict` policy. `sources` on a matched row are `[theme_id, option_id, tag]` for each contributing tag, in decision order.

Outputs are the patched `MODEL`, the patched `CLIP`, and `report_json` (tags, public theme decisions, matched, skipped, applied, errors, notes). When the input clip was `None`, the clip output stays `None`.

Theme errors already stored on the result are copied into the aggregate report. They do not make Aggregate raise. Matching still uses the tags the result kept.

`on_error` is forwarded to `apply_loras` only:

- Outside ComfyUI, `comfy.sd.load_lora_for_models` is not importable. Aggregate leaves MODEL and CLIP unchanged, records a note, and does not raise. Each row has `loaded: false`.
- Inside ComfyUI, a missing or failing file is skipped on `passthrough` and recorded in `errors`. `raise` raises `ApplyError` and stops the loop.
- A `SchemaError` (the wires are not a library and a theme result) is not an apply failure. `passthrough` returns the input MODEL and CLIP and explains that in the report. `raise` propagates `SchemaError`.

## Editor

`js/` is a ComfyUI frontend extension (`WEB_DIRECTORY`). The extension name is `SystemOne.LoraRouter.UI`. It does not register a sidebar tab. The sidebar tab from the previous package is gone.

LoRA Library and Theme nodes grow an **Open visual editor** button (`serialize: false`). The same item is on the node right-click menu. It opens a modal. Theme Collect and LoRA Aggregate have no editor button.

The modal edits the same widgets the node runs. Valid edits are written after about 220ms. While the modal is visible, a 500ms poll reloads the form when `theme_json`, `enable_json`, `positive`, `negative`, or `run` changed outside the form. The poll does not run while a draft is invalid or a write is waiting. There is no widget-change hook. There is no **Apply to node** and no **Reload from node**.

Invalid fields are marked with the CSS class `s1-invalid` (red outline). An invalid draft is not written. For a Theme node the write is atomic: `theme_json`, `enable_json`, `positive`, `negative`, and `run` are written together, and only after both documents commit. If either document is invalid, nothing is written. Opening the editor reloads the widgets and drops an unsaved invalid draft.

`lora_id`, `theme_id`, and `option_id` are read-only in the form. The enable clause's upstream `theme_id` is an editable reference, labeled `upstream theme_id`. One strength field is labeled `strength (model & clip)`. Positive is above negative wherever prompts appear. JSON widgets set `dynamicPrompts` off. The LoRA name field can pick a file from the ComfyUI loras list (`LoraLoader`, then `LoraLoaderModelOnly`, then `/models/loras`). A typed name that is not in the list is still stored.

## Migration

Runtime parsing does not accept the old documents. `schema/migrate.py` is an offline helper: `migrate_theme_library`, `migrate_theme_document`, `retag_lora_library`, and `plan_sequence`. See [MIGRATION.md](MIGRATION.md). Copies of the old examples are in `examples/legacy/`.

## Known limitations

- The modal syncs by polling while it is visible. It does not subscribe to widget changes. Theme ids are still written before queue without opening the modal.
- Restored duplicate theme ids are reported and left unchanged. The extension cannot repair a prompt that never loads the graph in the browser.
- Numbering is per graph object (`app.graph`, and each `node.subgraph`). Other subgraph storage is not walked. A prompt built outside this extension is not renumbered.
- Tag match is exact any-overlap. `enabled_default: false` excludes a LoRA even when a tag matches.
- `rewrite_*`, per-binding strengths, and `strength_conflict` are not runtime behavior.
- Theme Collect merges an identical shared ancestor once and rejects a conflicting theme id. It is still a two-input node.
- There is no SystemOne answer preview in the editor.
- `apply_loras` does not patch weights outside ComfyUI.
- Invalid theme or enable JSON fails the theme node even when `on_error` is `passthrough`.
