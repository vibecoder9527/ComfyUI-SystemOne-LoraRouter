# ComfyUI-SystemOne-LoraRouter

ComfyUI custom nodes: SystemOne LoRA Router (theme library / LoRA library / theme sequence)

Three canvas nodes. LoRA Library and Theme Library feed Theme Sequence. Theme Sequence POSTs to SystemOne, aggregates LoRA bindings, and outputs MODEL. The contract is [SPEC.md](SPEC.md).

## Install

The folder name inside ComfyUI `custom_nodes` must stay `ComfyUI-SystemOne-LoraRouter`.

Clone:

```bash
cd /path/to/ComfyUI/custom_nodes
git clone <repo-url> ComfyUI-SystemOne-LoraRouter
```

Or symlink a checkout you already have:

```bash
ln -s /path/to/ComfyUI-SystemOne-LoraRouter /path/to/ComfyUI/custom_nodes/ComfyUI-SystemOne-LoraRouter
```

Restart ComfyUI after installing. This package uses the Python standard library only (`urllib.request`, `json`, `uuid`, `os`). `requirements.txt` lists no third-party packages, so there is nothing to pip-install.

The nodes show up under **SystemOne → LoraRouter**:

| Node | Class | Output |
| --- | --- | --- |
| LoRA Library | `S1LoraLibrary` | `S1_LORA_LIB` |
| Theme Library | `S1ThemeLibrary` | `S1_THEME_LIB` |
| Theme Sequence | `S1ThemeSequence` | `MODEL`, `CLIP`, `STRING` (`report_json`) |

Wire both libraries into Theme Sequence, along with `model`, the positive prompt (`positive`), and `sequence_json`. Connect the `CLIP` output only when a clip input is connected too. With no clip input, the second output is `None`.

Set the API key on Theme Sequence, or export `SYSTEM_ONE_API_KEY` and leave the widget blank. A non-empty widget wins. The default endpoint is `https://system-one.dev/v1/systemone`. A blank `api_model` becomes the fallback `unspecified`. SPEC §6 leaves the production model id open, so this package does not hard-code one. A live SystemOne call requires a key.

JSON widgets set `dynamicPrompts` off so `{` stays literal JSON.

## What this package runs

Validation of library, theme, and sequence JSON is real (`schema/types.py`). The walk in `sequence_engine.py` is real:

- `select_mode: single` sends a SystemOne `choice` question. If rewrite leaves one option, the step skips the call and takes that option.
- `select_mode: multi` sends one `noul` question per option. `noul >= noul_threshold` selects it. More than 32 options are split across requests that share the same state.
- Dependencies are OR. Each match runs its actions in order: `enable_step`, `disable_step`, `rewrite_options`, `rewrite_instructions`, `set_select_mode`. Rewrites edit a runtime copy of the theme. The Theme Library object stays as the library node built it.
- `on_error=passthrough` (the default) returns the input MODEL and CLIP and writes the failure into `report_json`. `raise` stops the graph. When ComfyUI is importable, a missing LoRA file is skipped on passthrough and listed in `errors`.

Invalid JSON on a library node fails that node. A library cannot be built from a broken document. Runtime failures belong to Theme Sequence's `on_error`.

**SystemOne HTTP** is live. `systemone/client.py` POSTs JSON with `Authorization: Bearer …` and `Idempotency-Key: <uuid4>` via `urllib.request`. Choice reads `answers[qid].choice`; noul reads `answers[qid].noul`. A missing key raises before a socket is opened.

**LoRA apply** uses `folder_paths.get_full_path`, `comfy.utils.load_torch_file`, and `comfy.sd.load_lora_for_models` when ComfyUI is importable (`clip` may be `None`). Outside ComfyUI it leaves MODEL and CLIP unchanged and says so in the report. Each applied row then has `loaded: false`. Unittest mocks those imports.

## Visual editors (v2)

The multiline JSON widgets are still the stored documents. The v2 editors change those same strings. Saving the workflow still writes the JSON onto the node. There is no fourth wire, and the prompt still sends the JSON widgets.

Restart ComfyUI after installing so it loads `js/` (`WEB_DIRECTORY`).

### How to open

1. Add a LoRA Library, Theme Library, or Theme Sequence node.
2. Open the sidebar tab **S1 Editors** (list icon). It edits the node you last opened from a button.
3. Or click **Open visual editor** on the node. That selects the node, focuses the S1 Editors tab, and loads that node's JSON widget. The same item is on the node right-click menu.
4. On a ComfyUI build without `app.extensionManager.registerSidebarTab`, the button opens a floating panel with the same editors.

| Node | Widget the editor writes | What the form edits |
| --- | --- | --- |
| LoRA Library | `library_json` | LoRA entries: id, file name, strengths, tags, enabled default |
| Theme Library | `library_json` | Themes, options, select mode, bindings, fallback and none ids |
| Theme Sequence | `sequence_json` | Steps, theme id, and dependencies |

### Using an editor

- **Reload from node** reads the widget again. **Open visual editor** does that too, so unapplied form edits are replaced by the widget text.
- **Apply to node** checks the form, writes pretty JSON into the widget, and marks the graph dirty. Typing does not write the widget.
- Invalid JSON shows the error and the original text. Fix it and choose **Try form**, or keep editing the multiline widget on the node. Apply does not replace the widget until the text parses.
- LoRA file names are typed by hand.

### Known limitations

- No live SystemOne API preview or dry-run from the UI.
- `rewrite_options` is a JSON object (`keep_option_ids`, `add_options`, `remove_option_ids`, `patch_bindings`). The other action types have fields.
- Requires a ComfyUI build that loads `WEB_DIRECTORY` extensions. Restart ComfyUI after install.
- The sidebar API differs across ComfyUI versions. If `registerSidebarTab` is missing, the node button opens a modal instead.
- Does not browse the `loras/` folder. Type file names manually.
- The multiline JSON widgets remain the power-user path. Graph serialization is unchanged: the workflow stores the JSON on the node.
- `meta` on a LoRA entry is kept on Apply, and the form does not edit it.

## Examples

| File | Contents |
| --- | --- |
| `examples/lora_library.empty.json` | Widget default |
| `examples/theme_library.empty.json` | Widget default |
| `examples/sequence.empty.json` | Widget default |
| `examples/*.minimal.json` | SPEC §5: two themes, one dependency, three LoRAs |

The minimal sequence is: prompt leans anime → s1 selects `anime` → enable s2, keep `waifu_a` → list `char_a` and `style_anime_v3`. Weights are patched only when the package runs inside ComfyUI and those files exist under `loras/`. Unittest mocks HTTP (and ComfyUI) so it needs no live key and no ComfyUI install.

## Check

```bash
python3 -m unittest tests.test_skeleton
```
