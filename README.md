# ComfyUI-SystemOne-LoraRouter

ComfyUI custom nodes that ask SystemOne which theme options fit a prompt, turn the selected options into tags, and apply each matching LoRA once.

Positive is the input above negative. Positive is required. Negative is optional; unconnected or blank is sent as empty. Prompts are sockets, not text stored on the theme.

The contract is [SPEC.md](SPEC.md). Moving a 51f1904 workflow, or an older theme library or sequence, is [MIGRATION.md](MIGRATION.md).

## Install

The folder name inside ComfyUI `custom_nodes` must stay `ComfyUI-SystemOne-LoraRouter`.

```bash
cd /path/to/ComfyUI/custom_nodes
git clone <repo-url> ComfyUI-SystemOne-LoraRouter
```

Or symlink a checkout you already have:

```bash
ln -s /path/to/ComfyUI-SystemOne-LoraRouter /path/to/ComfyUI/custom_nodes/ComfyUI-SystemOne-LoraRouter
```

Restart ComfyUI after installing. This package uses the Python standard library only. `requirements.txt` lists no third-party packages.

The nodes show up under **SystemOne → LoraRouter**:

| Node | Class | Output |
| --- | --- | --- |
| LoRA Library | `S1LoraLibrary` | `S1_LORA_LIB` |
| SystemOne Settings | `S1Settings` | `S1_SETTINGS` |
| Theme Root | `S1ThemeRoot` | 32 `S1_DECISION` option slots, then `report_json` |
| Theme | `S1Theme` | 32 `S1_DECISION` option slots, then `report_json` |
| Theme Collect | `S1ThemeCollect` | `S1_DECISION` |
| LoRA Aggregate | `S1LoraAggregate` | `MODEL`, `CLIP`, `report_json` |
| S1 Save Image (Scrubbed) | `S1SaveImageScrubbed` | `IMAGE` (output node, saves PNGs) |

`theme_result` and `S1_THEME_RESULT` are gone. `run` and `enable_json` are gone. API widgets live only on SystemOne Settings.

**S1 Save Image (Scrubbed)** works like core Save Image (`filename_prefix`, output folder, `_00001_` counter, preview, `--disable-metadata`), and the PNG still embeds `prompt` and `workflow` so it can be dragged back in. Before writing it clears SystemOne Settings `api_key` and `endpoint` to `""` in copies of the prompt and the workflow (positional `widgets_values`, subgraph definitions too), and removes those values everywhere else they appear, including through a linked Primitive or String node. Values shorter than 6 characters are only cleared in those fields. After writing it re-reads the PNG text chunks; if a value is still there it deletes the file(s) and fails. A reloaded workflow has a blank key (falls back to `SYSTEM_ONE_API_KEY`) and a blank endpoint (the SystemOne default).

## Wire a decision tree

`examples/wiring.art_and_character.json` is the same shape in words.

1. Add **SystemOne Settings**. Put the API key there, or leave it blank and export `SYSTEM_ONE_API_KEY`. A non-empty widget wins. The default endpoint is `https://system-one.dev/v1/systemone`. A blank `api_model` is sent as `unspecified`.
2. Add a **LoRA Library**. Paste `examples/lora_library.minimal.json`, or start from `examples/lora_library.empty.json` and use **Open visual editor**.
3. Add **Theme Root**. Paste `examples/theme.art_style.json` into `theme_json`. Wire Settings into `settings`. Wire a positive prompt into `positive`. Negative is optional; leave it unconnected or blank to send an empty negative. Positive is the input above negative. Theme Root always decides. There is no `run` switch.
4. Add **Theme**. Paste `examples/theme.character_pack.json`. Wire the same Settings node, and wire this theme's own prompts. Wire the root's **anime** option slot into this node's `upstream` input. That wire is what used to be `enable_json`.
5. Add **LoRA Aggregate**. Connect `MODEL`, the LoRA Library, and a selected option slot from the child Theme (or Theme Collect) into `decision`. Connect `CLIP` only when you want CLIP patched. With no clip input, the CLIP output is `None`.

Unselected option slots are `ExecutionBlocker` values. ComfyUI does not run the nodes wired only to those slots. `none_option_id` still emits when it is chosen, and it contributes no tags.

The character theme's options contribute `char_a` and `char_b` when the anime slot fired and both noul scores pass. The library entry `char_a` has tag `char_a`, so Aggregate applies `character_a.safetensors` at `0.9` / `0.9`. Option `anime` contributes `style_anime`, which applies `anime_style_v3.safetensors` at `0.8` / `0.8`. Option `none` does not contribute `should_not_apply`. `char_b` matches no library entry.

A theme has at most 32 option slots. `report_json` stays at output index 32. The editor hides unused slots.

Theme Collect joins two `S1_DECISION` payloads when two branches should apply together:

```
root anime slot ──► Theme A ──► Theme Collect ──► LoRA Aggregate
              └──► Theme B ──┘
```

Collect keeps the first copy of each `theme_id`. The same decision is stored once. A different decision for that id raises `SchemaError`. Inputs start as optional `a` and `b` so saved wires stay. Connecting a slot offers another empty one. An `ExecutionBlocker` or missing optional input is ignored so a selected option slot can stay linked and Collect can run. Zero usable inputs raises `SchemaError`. Chain Collect to merge more than two payloads.

`on_error=passthrough` on Settings records an API or choice failure, adds no tags from that theme, and still emits the accumulated payload on every real option slot so a wired Aggregate can keep upstream tags. `on_error=raise` stops the graph. Invalid `theme_json` is not that path: it raises `SchemaError`, and the graph stops. Aggregate's own `on_error` applies to weight loading only.

JSON widgets set `dynamicPrompts` off so `{` stays literal JSON.

## What a decision does

- Theme Root always decides when its inputs are valid. A downstream Theme decides because its parent option slot emitted. An `ExecutionBlocker` on `upstream` does not call SystemOne.
- `single` sends a SystemOne `choice` question. One remaining option is selected without a call. An unknown choice fails. A confidence below `min_confidence` is kept and noted. There is no `fallback_option_id`.
- `multi` sends one `noul` question per option. A score at or above `noul_threshold` (default `0.5`) selects it. The node refuses more than 32 options before any HTTP call.
- LoRA Aggregate always applies a LoRA when `enabled_default` is true. When `enabled_default` is false, it applies only if any of its tags was contributed. The same `lora_id` is applied once, in `lora_id` order, at the library strengths.
- A multi theme that selects nothing blocks every option slot. Upstream tags stay on that result and are not emitted. Wire Aggregate to an upstream slot if those tags must flow.
- A theme with zero options records an error and blocks every slot. Nothing downstream of that node runs.

Outside ComfyUI, weight files are not patched. The aggregate report says so. Inside ComfyUI, a missing file is skipped on passthrough and listed in `errors`.

The HTTP client is live (`systemone/client.py`): POST JSON, `Authorization: Bearer …`, `Idempotency-Key: <uuid4>`. Tests mock `urllib` and do not send a request. The key is never written into `report_json`.

## Visual editor

The sidebar tab is gone. Nothing in this package registers an S1 Editors sidebar.

**Open visual editor** sits on LoRA Library, Theme Root, and Theme. It also appears on the node right-click menu. The button opens a modal. Theme Collect, LoRA Aggregate, and SystemOne Settings do not have the button.

Valid edits reach `theme_json` or `library_json` after about 220ms. Invalid fields get a red outline (`s1-invalid`) and are not written. There is no Apply to node button and no Reload from node button. The editor does not write prompts, `run`, or `enable_json`.

`lora_id`, `theme_id`, and `option_id` are assigned automatically and shown in titles, not as form fields. A default None option is always present, with its own output slot; an existing None-like option is reused so slot indexes stay put. Option tags can be picked from tags already used on LoRA Library and Theme nodes in the graph. The LoRA Library editor uses compact rows: on/off, name, strength, and tags. Adding or duplicating a Theme or Theme Root writes the next free `theme_N` into `theme_json` before the prompt is queued, including when this modal stays closed. A saved non-empty id that is unique on the loaded graph stays, including a manual id such as `art_style`. If a loaded workflow has two theme nodes with the same non-empty `theme_id`, both documents are left as saved and the node title notes a theme_id conflict. A decision chain still rejects a repeated theme_id. One strength control writes `strength_model` and `strength_clip`. The LoRA name can be picked from the ComfyUI loras list or typed.

After a valid theme write, and again when a graph is configured or queued, the editor renames option sockets to `label (option_id)`. Unused pads that have no live wire are omitted from the visible output list so only defined options show. A connected socket is never removed. ComfyUI 0.44 / frontend 1.57.6 drops a wire when a *connected* socket is hidden or when `output.links` is assigned. It stores the wire in `graph.links` (`origin_id` / `originId`, `origin_slot` / `originSlot`) even when `output.links` is empty. The sync reads that record. It does not assign `output.links`, because that setter disconnects the link. The first sync stamps ids by index and does not move wires. A later sync moves wires by `option_id`. A wire with no stamped id stays connected. Deleting an option in the editor disconnects that option's own wires, because its slot is renumbered to the next option. `report_json` stays at index 32.

Restart ComfyUI after installing so it loads `js/`.

## Tests

From the repo root:

```bash
python3 -m unittest
python3 -m compileall -q -f .
node --check js/s1_model.js
node --check js/s1_editors.js
```

Unittest discovers `tests/test_*.py`. It does not call SystemOne and does not need an API key. No browser pass is part of this suite. The editor checks are source and model tests, not a click-through in ComfyUI.

## Limitations

- A live graph skips unselected slots only when this package returns ComfyUI's `ExecutionBlocker`. Without ComfyUI, the node returns a local stand-in with the same `message`. Tests assert that stand-in. `message is None` is the silent skip.
- The node always exposes 32 option sockets plus `report_json`. Unused sockets stay visible with the label `·` so frontend 1.57.6 does not strip their wires. A socket past the option list still returns a blocker, so a wire on it does not run downstream work when ComfyUI's blocker is in use.
- The first editor sync does not move existing wires. A saved link that used to be `theme_result` on output 0 is treated as option 0 until you retarget it. `migrate_router_graph` warns instead of guessing.
- `on_error=passthrough` emits on every real option slot, so children of those slots run. That is wider than the old enable-rule skip.
- A multi theme with zero selections, and a theme with zero options, do not emit upstream tags on a slot.
- Theme Collect ignores a blocked or missing optional input and keeps the other decision. Two real payloads still merge, and a conflict still raises. Zero usable inputs raises `SchemaError`. ComfyUI 0.44 skips a node when *any* input, including an optional one, is an `ExecutionBlocker`. On load, this pack wraps `_async_map_node_over_list` so Collect's optional blocked siblings are treated as disconnected. Mixed optional batches keep live items and skip only the blocked slices. Required-input blockers (a child Theme, LoRA Aggregate, KSampler) still skip. The opt-in flag must be declared on the node class itself; subclasses do not inherit it silently. If the wrapper cannot be installed, a `ThemeCollectHookWarning` is emitted and Collect stays fail-closed: a blocked sibling still skips Collect and downstream generation does not run. The hook is installed at most once; if a later wrapper displaces it, another copy is not stacked.
- Modal sync polls about every 500ms while the modal is visible. It does not hook widget changes. Theme ids and option labels are still written before queue without opening the modal.
- Numbering runs in the browser on each loaded graph, including each nested `node.subgraph` as its own id space. A workflow that is not loaded is unchanged.
- A restored duplicate `theme_id` is reported and not rewritten. Queueing those nodes in one result still raises `SchemaError`.
- Tag match is an exact string overlap. `enabled_default: true` is always-on (no tag required). `enabled_default: false` is tag-gated (apply only on overlap).
- Old `lora_bindings` and per-binding strengths are not applied at runtime. See MIGRATION.
- `apply_loras` is a no-op when ComfyUI is not importable.
- There is no in-editor preview of a SystemOne answer.

## On-node editors (Vue Nodes 2.0)

Theme Root / Theme and LoRA Library draw their editors on the node (`addDOMWidget`). `theme_json` and `library_json` stay hidden widgets so saved workflows migrate losslessly. Theme options show None last, and `option_id` follows the table: `option_N` is row N and output slot N (None has the last id). Move up/down swaps the two rows and their ids; Delete renumbers the rows below it. Downstream wires follow their option (`graph.links` `origin_slot` is remapped; `output.links` is never assigned), and the wires of a deleted option are disconnected. A loaded workflow whose ids disagree with the table (for example None=`option_2`, dress=`option_3`) is renumbered once on load with its wires remapped; a consistent one is left as is. `report_json` files written earlier keep the ids they had then. Compact/expand with `s1PromptIndex` is unchanged. Tags use chip inputs (Enter or comma). Add Lora opens a LiteGraph context menu nested by folder; a row is added only after a pick (enabled_default on, strength 1.00).

