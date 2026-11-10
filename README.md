English | [繁體中文](README_zh-TW.md)

# ComfyUI-SystemOne-LoraRouter

ComfyUI custom nodes that ask SystemOne which theme options fit your prompt, turn the chosen options into tags, and load the LoRAs that match those tags.

Positive is the input above negative on every Theme node. Positive is required. The negative prompt is optional; unconnected or blank is sent as empty. Prompts are sockets, not text stored in the theme.

The full contract is [SPEC.md](SPEC.md). Upgrading an older workflow (`enable_json`, `theme_result`, theme libraries, sequences) is covered in [MIGRATION.md](MIGRATION.md).

## Install

The folder inside `custom_nodes` must be named `ComfyUI-SystemOne-LoraRouter`.

```bash
cd /path/to/ComfyUI/custom_nodes
git clone <repo-url> ComfyUI-SystemOne-LoraRouter
```

Restart ComfyUI, then hard-refresh the browser so the frontend files in `js/` load. There are no extra Python packages to install; the save node uses the numpy and Pillow that ComfyUI already ships.

## Nodes

All nodes are under **SystemOne → LoraRouter**.

| Node | Class | Purpose | Output |
| --- | --- | --- | --- |
| SystemOne Settings | `S1Settings` | API key, endpoint, model, thresholds, error policy | `S1_SETTINGS` |
| LoRA Library | `S1LoraLibrary` | The LoRAs you can route to, with tags and strengths | `S1_LORA_LIB` |
| Theme Root | `S1ThemeRoot` | First decision: always asks SystemOne | 32 `S1_DECISION` option slots, then `report_json` |
| Theme | `S1Theme` | Follow-up decision: runs only when its `upstream` slot fired | 32 `S1_DECISION` option slots, then `report_json` |
| Theme Collect | `S1ThemeCollect` | Merges decisions from sibling branches | `S1_DECISION` |
| LoRA Aggregate | `S1LoraAggregate` | Matches tags to the library and loads the LoRAs | `MODEL`, `CLIP`, `report_json` |
| S1 Save Image (Scrubbed) | `S1SaveImageScrubbed` | Save Image without the SystemOne key or URL in the PNG | `IMAGE` (output node) |

## Basic wiring

```
SystemOne Settings ──► Theme Root.settings ──(option slot)──► Theme.upstream ──(option slot)──► LoRA Aggregate.decision
positive / negative ──► Theme Root, Theme                              LoRA Library ──► LoRA Aggregate.lora_lib
                                                                       MODEL / CLIP ──► LoRA Aggregate ──► sampler
```

1. **SystemOne Settings**: enter `api_key`, or leave it blank and set the `SYSTEM_ONE_API_KEY` environment variable (a non-empty widget wins). `endpoint` defaults to `https://system-one.dev/v1/systemone`. A blank `api_model` is sent as `unspecified`. `noul_threshold` (default 0.5) and `min_confidence` (default 0) tune selection. `on_error`: `passthrough` records an API failure, adds no tags from that theme and still emits on every option slot; `raise` stops the graph.
2. **LoRA Library**: add your LoRAs and tags (see below).
3. **Theme Root**: wire Settings into `settings` and your prompt into `positive` (`negative` is optional). Fill in the option table.
4. **Theme** (optional, any depth): wire the same Settings, its own prompts, and one option slot of a parent theme into `upstream`. It runs only when that option was chosen.
5. **LoRA Aggregate**: wire `MODEL`, the library into `lora_lib`, and the option slot (or Theme Collect) whose tags should apply into `decision`. Wire `CLIP` only if CLIP should be patched; without it the CLIP output is `None`.

An option slot that was not chosen outputs an `ExecutionBlocker`, so ComfyUI skips the nodes wired only to it. The None option still emits when chosen and contributes no tags.

## LoRA Library (on-node editor)

The library is edited directly on the node; the `library_json` widget stays hidden and is what gets saved.

- **＋ Add Lora** opens a LoRA chooser (folders as submenus, type to filter). A row is added only after you pick a file. New rows have Default On enabled and strength 1.00.
- Click a row's name to pick a different file.
- **Default On**: on means the LoRA is always loaded. Off means it loads only when one of its tags is chosen by a theme.
- **Strength**: ◀ / ▶ step by 0.05, drag horizontally, or type a value. One value is written to both `strength_model` and `strength_clip`.
- **S** marks the entry as a slider LoRA, which allows strengths from −5 to 5. Unmarking resets a negative strength to 0.
- **Tags** are chips: type and press Enter or comma, Backspace removes the last chip, × removes one, click a chip to edit it. Suggestions come from tags already used on the graph. Library tags are plain names (no weights).
- Right-click a row for **Move up**, **Move down**, **Mark as Slider** / **Unmark Slider**, and **Delete**.

## Theme Root / Theme (on-node editor)

The theme is edited on the node; the `theme_json` widget stays hidden.

- The text box at the top is the theme's instructions for SystemOne.
- The option table has **Option** (row number), **Description**, and **Tags (Comma)**. Description is what SystemOne reads for that option. Tags are what the option contributes when chosen.
- **Add option** adds a row above None.
- **None** is always the last row. It cannot be moved or deleted, has its own output slot, and contributes no tags. Its id is stored as `none_option_id` in `theme_json`.
- **`option_N` is always row N.** Option ids are renumbered from the table order, so `report_json` and output slot N always mean row N (None has the last id).
- Right-click a row for **Move up**, **Move down**, or **Delete**. Moving swaps the two rows together with their ids, and any wires on those output slots follow their option. Deleting renumbers the rows below it; their wires move up with them, and the deleted option's own wires are disconnected.
- A workflow saved with ids out of order (for example None = `option_2`, dress = `option_3`) is renumbered once when it loads, with its wires remapped. Older `report_json` files keep the ids they were written with.
- Output sockets are labeled with the option text. Unused sockets are hidden; `report_json` is always output index 32 in the saved prompt. A theme has at most 32 options.
- `select_mode` lives in `theme_json`: `single` (default) asks one choice question; `multi` asks a yes/no score per option and selects every option at or above `noul_threshold`. The on-node editor keeps whatever is stored.

## Slider LoRAs: `tag:weight`

In a theme option's tags you can write `name:weight`, for example `age:-2`, `age:0`, `age:1.5` (`+1.5` also works). A plain `age` still works as before.

- Matching is by name only and case-insensitive: option tag `Age:-2` matches library tag `age`.
- A weighted hit overrides both strengths of that LoRA. An unweighted hit keeps the library strengths.
- Weight `0` skips the LoRA, even if Default On is enabled (listed under `skipped` with reason `weight_0`).
- If several chosen options give different weights to the same LoRA, the one with the largest absolute value wins; a tie keeps the first.
- Weights outside −5..5 are clamped to that range with a warning.
- A negative weight on a LoRA that is not marked as a slider is still applied, with a warning.
- Chips show weights as `age −2`.

The decision request to SystemOne does not include any tags.

## Theme Collect

Use Collect when two sibling branches should apply together:

```
Theme Root slot ──► Theme A ──► Theme Collect ──► LoRA Aggregate
                └─► Theme B ──┘
```

Inputs start as `a` and `b`; connecting one shows another empty input (up to 16). Inputs whose branch did not run are ignored, so Collect still runs when only one branch fired. With no usable input it raises an error. The same theme decided twice is stored once; two different decisions for the same `theme_id` raise an error.

## report_json

- **Theme / Theme Root**: `theme_id`, `role`, `status`, `selected` option ids, the theme's `tags`, all upstream `decisions`, `accumulated_tags`, `errors`, `slots` (`{option_id, emitted}` per option), `api` (`called`, `endpoint`, `model`, `key_source`), and `notes`. The API key is never included.
- **LoRA Aggregate**: `tags`, `themes`, `matched` (with `weight_source` and `slider`), `skipped`, `applied`, `errors`, `notes`, and `warnings`.

## S1 Save Image (Scrubbed)

Works like the core **Save Image** node: `filename_prefix`, the ComfyUI output folder, `prefix_00001_.png` counter names, preview in the UI, and `--disable-metadata` support. The PNG still embeds `prompt` and `workflow`, so you can drag it back into ComfyUI.

Before writing, it clears the SystemOne Settings `api_key` and `endpoint`:

- in the prompt and in the workflow (including subgraphs), set to `""`; a reloaded workflow then uses `SYSTEM_ONE_API_KEY` and the default endpoint;
- everywhere else those values appear in the metadata, including values fed in through a linked Primitive or String node (values shorter than 6 characters are only cleared in the Settings fields).

After saving it re-reads the PNG. If a cleared value is still present, it deletes the file and fails. Nothing else in the metadata is changed. Use it instead of Save Image when you share images.

## Notes and limits

- Theme Collect relies on a small hook into ComfyUI 0.44's executor so a skipped sibling does not skip Collect. If the hook cannot be installed, a `ThemeCollectHookWarning` is shown and Collect stays fail-closed.
- A `multi` theme that selects nothing blocks every option slot. A theme with no options is an error (handled by `on_error`).
- Outside ComfyUI (for example in tests) LoRA files are not loaded; the report says so.

## Tests

```bash
python3 -m unittest
```

Tests do not call SystemOne and do not need an API key. JS model tests run when `node` is installed. There is no browser click-through in this suite.
