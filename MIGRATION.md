# Migration from theme library and theme sequence

This package no longer registers `S1ThemeLibrary` or `S1ThemeSequence`. Workflows that used those nodes do not load the old classes. The runtime parsers reject `lora_bindings`, `fallback_option_id`, and a `themes` list. There is no compatibility mode that still executes a sequence.

`schema/migrate.py` rewrites JSON. It does not register nodes and it does not call SystemOne. Run it while editing, then paste the results onto Theme nodes and the LoRA Library.

Old example documents are kept in `examples/legacy/` (`theme_library.*.json`, `sequence.*.json`, and the library file from that era). The active examples under `examples/` are the new documents.

## What you build instead

| Old | New |
| --- | --- |
| `S1ThemeLibrary` / `S1_THEME_LIB` | One `S1Theme` node per theme. `theme_json` is one theme object. |
| `S1ThemeSequence` / `sequence_json` | Chain Theme nodes. `run=enabled` replaces a step that started enabled. `run=when_upstream` plus `enable_json` replaces `enable_step`. |
| Option `lora_bindings` | Option `tags`. LoRA Aggregate matches tags on `S1LoraLibrary` entries. |
| Per-binding `strength_model` / `strength_clip` | Dropped. Aggregate uses the library strengths and applies each `lora_id` once. |
| `strength_conflict` (`max`, `sum_clamp_1`, `last_wins`) | Removed. One library strength, one apply. |
| `fallback_option_id` | Removed. A low-confidence choice is kept. `none_option_id` still means "this option contributes no tags". |
| `rewrite_options`, `rewrite_instructions`, `set_select_mode` | Not migrated into behavior. Edit the Theme document by hand. `plan_sequence` warns. |
| `disable_step` | Not migrated. A theme does not turn off conditionally. `plan_sequence` warns. |
| Sidebar tab **S1 Editors** | Removed. **Open visual editor** opens a modal on the node. |

`S1LoraLibrary` stays. Add `tags` to each entry you want Aggregate to select. The file name and the strengths stay on the entry. Manual ids stay. Blank ids are filled with `lora_N`, `theme_N`, or `option_N` by the editor and by the migration helper, not by the runtime parser.

## Theme library to theme documents

```python
import json
from schema.migrate import migrate_theme_library, retag_lora_library

library = json.load(open("examples/legacy/theme_library.minimal.json", encoding="utf-8"))
migrated = migrate_theme_library(library)
for item in migrated:
    print(item.notes)
    print(json.dumps(item.document, ensure_ascii=False, indent=2))
```

Rules:

- A library's `themes` list becomes one document per theme. A single theme object is accepted too. `migrate_theme_document` requires exactly one.
- Bindings and no `tags`: the tags become the bound `lora_id` values, in order, without duplicates. The note tells you to retag the LoRA library or set matching tags yourself.
- Bindings and existing `tags`: the tags are kept and the bindings are dropped, with a note.
- A binding strength is dropped, with a note. It is not copied onto the library.
- `fallback_option_id` is dropped, with a note, and is not applied.
- Manual `theme_id` and `option_id` values are kept. A blank id is filled. The result is passed through `parse_theme`. If the old theme is still invalid (empty title, bad `select_mode`, `none_option_id` pointing at a missing option), migration raises `SchemaError` instead of emitting a document.

`examples/theme.art_style.json` and `examples/theme.character_pack.json` are the hand-written form of the old minimal library: tags are `style_anime`, `style_realistic`, `char_a`, and `char_b`, not the raw `lora_id` strings, and the library strengths are `0.8/0.8`, `0.7/0.7`, and `0.9/0.9`. The old binding override `0.85` on `style_anime_v3` is not used.

## Point the library at those tags

```python
lora = json.load(open("examples/lora_library.minimal.json", encoding="utf-8"))
updated, notes = retag_lora_library(lora, [item.document for item in migrated])
```

`retag_lora_library` appends a tag onto a library entry when an option tag equals that entry's `lora_id` and the tag is not already there. It does not rewrite strengths or ids. A tag that equals no `lora_id` is left on the option and mentioned in the notes. The active minimal library already uses descriptive tags (`style_anime`, not `style_anime_v3`), so retag will not add those descriptive tags for you. Set them on the entries, as in `examples/lora_library.minimal.json`.

## Sequence to a run plan

```python
from schema.migrate import plan_sequence
plan = plan_sequence(open("examples/legacy/sequence.minimal.json", encoding="utf-8").read())
```

`plan_sequence` is advisory. It does not execute steps.

- `enabled_by_default: true` and no `disable_step` becomes `run: enabled`. Enable clauses are not required for that node. If the step also had `enable_step` actions, the plan warns that those clauses are not what turns the theme on.
- A step that starts disabled and has an `enable_step` action becomes `run: when_upstream`. Each `when` becomes a clause. The clause's `theme_id` is the referenced step's `theme_id`, not the old `step_id`.
- A step that starts disabled and has no `enable_step` becomes `run: disabled`.
- `rewrite_*` and `disable_step` become warnings.
- The same `theme_id` on more than one step is a warning. A result chain requires unique theme ids.
- The plan's `removed` list names `S1ThemeLibrary`, `S1ThemeSequence`, `lora_bindings`, `fallback_option_id`, `strength_conflict`, and `sequence_json`.

For `examples/legacy/sequence.minimal.json` the plan is: art style `run=enabled`, character pack `run=when_upstream` with `includes_any` / `anime` on theme `art_style`. The `rewrite_instructions` and `rewrite_options` actions are warnings. The character theme in `examples/theme.character_pack.json` still lists both `waifu_a` and `waifu_b`. The old rewrite that dropped `waifu_b` is not applied. Delete that option yourself if you still want it gone.

Paste each planned `enable_json` onto the matching Theme node and set `run`. Connect `theme_result` to the next theme's `upstream`, then connect the last result to `S1LoraAggregate` (LoRA Aggregate) with the library and MODEL. Use `S1ThemeCollect` only when the two results do not already share a theme id.

## Checks after you paste

- Every calling theme has an API key widget or `SYSTEM_ONE_API_KEY`. Disabled themes do not call.
- Theme ids are unique along a chain.
- Option tags and library tags are the same strings. Matching is case-sensitive.
- `none_option_id` still names an option, and that option contributes no tags.
- Positive stays above negative on each Theme.
