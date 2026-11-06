# ComfyUI-SystemOne-LoraRouter

ComfyUI custom nodes that ask SystemOne which theme options fit a prompt, turn the selected options into tags, and apply each matching LoRA once.

The contract is [SPEC.md](SPEC.md). Moving an old theme library or theme sequence onto these nodes is [MIGRATION.md](MIGRATION.md).

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
| Theme | `S1Theme` | `S1_THEME_RESULT`, `report_json` |
| Theme Collect | `S1ThemeCollect` | `S1_THEME_RESULT` |
| LoRA Aggregate | `S1LoraAggregate` | `MODEL`, `CLIP`, `report_json` |

`S1ThemeLibrary` and `S1ThemeSequence` are removed. Do not look for them on the canvas.

## Wire a decision tree

Themes default to `disabled`. A disabled theme does not call SystemOne and does not add tags.

1. Add a LoRA Library and paste `examples/lora_library.minimal.json`, or start from `examples/lora_library.empty.json` and use **Open visual editor**.
2. Add a Theme. Set `run` to `enabled`. Paste `examples/theme.art_style.json` into `theme_json`. This is the root. `enable_json` may stay `examples/enable.empty.json`.
3. Add another Theme. Set `run` to `when_upstream`. Paste `examples/theme.character_pack.json` and `examples/enable.when_anime.json`. Connect the first Theme's `theme_result` to this node's `upstream` input.
4. Add LoRA Aggregate. Connect `MODEL`, the LoRA Library, and the last Theme's `theme_result`. Connect `CLIP` only when you want CLIP patched. With no clip input, the CLIP output is `None`.

`when_upstream` turns the second theme on only when the upstream selection matches the clauses. `enable.when_anime.json` matches theme `art_style` when the selection includes option `anime`. That is selected-option targeting, not a bare on/off flag. A later theme can also target `eq`, `neq`, `includes_all`, `skipped`, or `answered`. See SPEC for the match table.

Put further themes on the same chain. Each output already contains the upstream decisions, so the next theme can target any earlier `theme_id`. A theme whose clauses miss simply records `skipped` and passes the earlier tags through.

Theme Collect joins two results. Decisions already in input `a` stay first. The same decision for a `theme_id` that is already present is kept once, so two branches that share an ancestor can meet:

```
A ──► B ──► Theme Collect ──► LoRA Aggregate
 └──► C ──┘
```

Collect(B, C) keeps A's decision once, then B, then C. Tags from A are not doubled. A different decision for the same `theme_id` raises `SchemaError`. Chain Collect to merge more than two results. A single chain, with no Collect, still works.

The character theme runs only after the art-style theme selects `anime`. Its options contribute tags `char_a` and `char_b`. The library entry `char_a` has tag `char_a`, so Aggregate applies `character_a.safetensors` at the library strength `0.9` / `0.9`. The art-style option `anime` contributes `style_anime`, which applies `anime_style_v3.safetensors` at `0.8` / `0.8`. Option `none` is `none_option_id`. If it is selected, its tag `should_not_apply` is not contributed. `char_b` matches no library entry, so it adds no LoRA.

Each theme has its own positive and negative prompts. Positive is the widget above negative. A blank negative is sent as `""`. Prompts are not copied from the upstream theme.

Set the API key on each Theme that calls SystemOne, or export `SYSTEM_ONE_API_KEY` and leave the widget blank. A non-empty widget wins. Disabled themes do not call the API. The default endpoint is `https://system-one.dev/v1/systemone`. A blank `api_model` becomes `unspecified`.

JSON widgets set `dynamicPrompts` off so `{` stays literal JSON.

## What a run does

- `run=disabled` parses the documents, appends a skipped decision, and returns. No HTTP.
- `run=enabled` always decides. Stored enable rules do not gate it.
- `run=when_upstream` decides only when the clauses match. An empty clause list matches nothing.
- `single` sends a SystemOne `choice` question. One remaining option is selected without a call. An unknown choice fails. A confidence below `min_confidence` is kept and noted. There is no `fallback_option_id`.
- `multi` sends one `noul` question per option. A score at or above `noul_threshold` (default `0.5`) selects it. More than 32 options are split across requests.
- LoRA Aggregate keeps a LoRA when any of its tags was contributed and `enabled_default` is true. The same `lora_id` is applied once, in `lora_id` order, at the library strengths.
- `on_error=passthrough` on a Theme records the API or choice failure and keeps upstream tags. Invalid JSON is not that path: it raises, and the graph stops. Aggregate's `on_error` applies to weight loading. A bad wire on passthrough returns the input MODEL and CLIP.

Outside ComfyUI, weight files are not patched. The aggregate report says so. Inside ComfyUI, a missing file is skipped on passthrough and listed in `errors`.

The HTTP client is live (`systemone/client.py`): POST JSON, `Authorization: Bearer …`, `Idempotency-Key: <uuid4>`. Tests mock `urllib` and do not send a request.

## Visual editor

The sidebar tab is gone. Nothing in this package registers an S1 Editors sidebar.

**Open visual editor** sits on LoRA Library and Theme. It also appears on the node right-click menu. The button opens a modal and edits that node's widgets. Theme Collect and LoRA Aggregate do not have the button.

Valid edits reach the widgets after about 220ms. Invalid fields get a red outline (`s1-invalid`) and are not written. A Theme write updates `theme_json`, `enable_json`, `positive`, `negative`, and `run` together, or it updates none of them. There is no Apply to node button and no Reload from node button.

`lora_id`, `theme_id`, and `option_id` are read-only in the form. The theme id shown is the id stored on that node. Adding or duplicating a Theme writes the next free `theme_N` into `theme_json` before the prompt is queued, including when this modal stays closed. The first new theme keeps `theme_1`. The next becomes `theme_2`, filling gaps. A saved non-empty id that is unique on the loaded graph stays, including a manual id such as `art_style`. Enable JSON is not edited, so a copied clause still names the upstream theme. If a loaded workflow has two Theme nodes with the same non-empty `theme_id`, both documents are left as saved and the node title notes a theme_id conflict. That avoids pointing a saved enable rule at a different node. Enable clauses use an editable **upstream theme_id**. One strength control writes `strength_model` and `strength_clip`. The LoRA name can be picked from the ComfyUI loras list or typed.

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

- Modal sync polls about every 500ms while the modal is visible. It does not hook widget changes. Theme ids are still written before queue without opening the modal.
- Numbering runs in the browser on each loaded graph, including each nested `node.subgraph` as its own id space. A workflow that is not loaded is unchanged. An API client that queues saved JSON without this extension uses the ids already in that JSON.
- A restored duplicate `theme_id` is reported and not rewritten. Queueing those nodes in one result still raises `SchemaError`. That is the conflict, not a retargeted enable rule.
- Tag match is an exact string overlap. A LoRA with `enabled_default: false` is skipped even when a tag matches.
- Old `lora_bindings`, per-binding strengths, `strength_conflict`, and `rewrite_*` actions are not applied at runtime.
- Theme Collect merges an identical shared ancestor once and rejects a conflicting `theme_id`. It still has two inputs; chain it for more than two results. One Theme still refuses to run when its own `theme_id` is already upstream.
- `apply_loras` is a no-op when ComfyUI is not importable.
- There is no in-editor preview of a SystemOne answer.
