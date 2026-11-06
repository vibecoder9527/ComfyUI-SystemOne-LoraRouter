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

Wire both libraries into Theme Sequence, along with `model`, the positive prompt (`positive`), and `sequence_json`. The negative prompt (`negative`) is the widget directly under `positive`. A blank negative is sent as `""`. Connect the `CLIP` output only when a clip input is connected too. With no clip input, the second output is `None`.

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
| LoRA Library | `library_json` | LoRA entries: read-only auto id (`lora_1`, `lora_2`, ...), file name (`name`), one strength for model and clip, tags, enabled default |
| Theme Library | `library_json` | Themes, options, select mode, bindings, fallback and none ids |
| Theme Sequence | `sequence_json`, `positive`, `negative` | Prompts (positive, then negative), steps, theme id, and dependencies |

### Using an editor

- **Reload from node** reads the widget again. **Open visual editor** does that too, so unapplied form edits are replaced by the widget text. On Theme Sequence it also reloads `positive` and `negative`.
- **Apply to node** checks the form, writes pretty JSON into the widget, and marks the graph dirty. Typing does not write the widget. On Theme Sequence one Apply writes `positive`, `negative`, and `sequence_json` together. Invalid sequence JSON blocks that write, including the prompts.
- Invalid JSON shows the error and the original text. Fix it and choose **Try form**, or keep editing the multiline widget on the node. Apply does not replace the widget until the text parses.

### LoRA file name

Each entry's `name` is the relative file name under ComfyUI `models/loras`, the same string the stock Lora Loader shows. SPEC has no separate path field. The picker writes that string into `name`.

- Type a name yourself. The text box stays editable, and its suggestions use the same list when ComfyUI returned one.
- **Browse loras…** opens a filterable list on that entry. Choosing a row copies the relative name into `name`. **Hide lora list** closes it.
- **Refresh loras** asks ComfyUI again. The editor reads `/object_info` for `LoraLoader` or `LoraLoaderModelOnly` and uses the `lora_name` combo. If that list is missing, it tries `api.getModels("loras")` and then `/models/loras`.
- **Apply to node** is what saves the name into `library_json`. The picker does not copy or rename files on disk.
- A name that is not in the current list is kept. Apply still writes it.

### LoRA id and strength

The LoRA Library form does not edit `lora_id`. The card title and a read-only field show it. **Add LoRA** assigns the smallest free id, `lora_1`, then `lora_2`, filling gaps such as a missing `lora_2`. Apply fills a missing or blank id the same way before it writes `library_json`. An id that is already set is kept, including older manual ids such as `style_anime_v3`. Theme bindings are not rewritten. They still cite `lora_id` by hand.

The library form has one control, **strength (model & clip)**. Apply writes that number to both `strength_model` and `strength_clip`. The stored JSON does not gain a `strength` key, and both keys stay required. If a loaded entry has two different strengths, the form shows `strength_model`, and the next Apply copies that value onto `strength_clip`. Theme option bindings still have their own optional `strength_model` and `strength_clip` boxes. A blank binding strength still means the library default.

Old library JSON keeps working. Manual ids stay. Entries that already store different `strength_model` and `strength_clip` values still validate. Apply is what copies one number onto both keys.

### Prompts on Theme Sequence

The Theme Sequence editor starts with **Prompts**: the positive textarea, then the negative textarea directly under it. Those boxes are the node widgets `positive` and `negative`. They are not fields inside `sequence_json`.

On the node, `negative` is a required multiline string directly under `positive`. `clip` stays optional. A blank negative is still sent as `""`.

### Known limitations

- No live SystemOne API preview or dry-run from the UI.
- `rewrite_options` is a JSON object (`keep_option_ids`, `add_options`, `remove_option_ids`, `patch_bindings`). The other action types have fields.
- Requires a ComfyUI build that loads `WEB_DIRECTORY` extensions. Restart ComfyUI after install.
- The sidebar API differs across ComfyUI versions. If `registerSidebarTab` is missing, the node button opens a modal instead.
- The LoRA list needs a running ComfyUI. It is empty when ComfyUI is offline, when `/object_info` has no `lora_name` list, or when `models/loras` has no files. The editor stays usable: type the relative name. Typed names still work and are what `name` stores.
- The list is relative names (`folder/file.safetensors`), not a full disk path. **Refresh loras** after you add files. ComfyUI rebuilds that combo when `/object_info` is requested.
- Workflows saved before `negative` moved under `positive` may have stored widget values by position. Builds that save widget names reload the right fields. If an old workflow only has an ordered values list, check that `negative` did not land in `sequence_json` the first time you open it.
- The multiline JSON widgets remain the power-user path. Graph serialization is unchanged: the workflow stores the JSON on the node. There is still no fourth sequence wire.
- `meta` on a LoRA entry is kept on Apply, and the form does not edit it.
- The LoRA Library editor does not keep different `strength_model` and `strength_clip` values on one entry. It shows `strength_model`, and Apply writes that number to both. Edit the JSON widget when one library entry must keep two strengths. Theme bindings can still override them separately.

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
