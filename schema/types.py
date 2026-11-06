"""Dataclasses and validators for LoRA libraries, theme libraries, and sequences.

SPEC §3. Version defaults to 1 when the field is omitted, so the widget defaults
`{ "loras": [] }`, `{ "themes": [] }`, and `{ "steps": [] }` validate.
Libraries are keyed by id. Theme JSON references `lora_id` only; file names
live on the LoRA entry.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

# Widget defaults from SPEC §2. Dynamic prompts must stay off on these fields
# so the braces are literal JSON.
EMPTY_LORA_LIBRARY_JSON = '{ "loras": [] }'
EMPTY_THEME_LIBRARY_JSON = '{ "themes": [] }'
EMPTY_SEQUENCE_JSON = '{ "steps": [] }'

SELECT_MODES = ("single", "multi")
WHEN_OPS_WITH_OPTIONS = ("eq", "neq", "includes_any", "includes_all")
WHEN_OPS_BARE = ("skipped", "answered")
WHEN_OPS = WHEN_OPS_WITH_OPTIONS + WHEN_OPS_BARE
ACTION_TYPES = (
    "enable_step",
    "disable_step",
    "rewrite_options",
    "rewrite_instructions",
    "set_select_mode",
)

_LORA_LIBRARY_KEYS = {"version", "loras"}
_LORA_ENTRY_KEYS = {
    "lora_id",
    "name",
    "strength_model",
    "strength_clip",
    "tags",
    "enabled_default",
    "meta",
}
_THEME_LIBRARY_KEYS = {"version", "themes"}
_THEME_KEYS = {
    "theme_id",
    "title",
    "instructions",
    "select_mode",
    "options",
    "none_option_id",
}
_OPTION_KEYS = {"option_id", "label", "description", "lora_bindings"}
_BINDING_KEYS = {"lora_id", "strength_model", "strength_clip"}
_SEQUENCE_KEYS = {"version", "steps"}
_STEP_KEYS = {"step_id", "theme_id", "enabled_by_default", "dependencies"}
_DEPENDENCY_KEYS = {"when", "actions"}
_WHEN_KEYS = {"step_id", "op", "option_ids"}
_ACTION_KEYS = {
    "enable_step": {"type"},
    "disable_step": {"type"},
    "rewrite_instructions": {"type", "instructions"},
    "set_select_mode": {"type", "select_mode"},
    "rewrite_options": {
        "type",
        "keep_option_ids",
        "add_options",
        "remove_option_ids",
        "patch_bindings",
    },
}


class SchemaError(ValueError):
    """Invalid library, theme, or sequence JSON. `path` locates the field."""

    def __init__(self, message: str, path: str = "") -> None:
        self.path = path
        self.message = message
        text = f"{path}: {message}" if path else message
        super().__init__(text)


@dataclass
class LoraEntry:
    lora_id: str
    name: str
    strength_model: float
    strength_clip: float
    tags: list[str] = field(default_factory=list)
    # False means "do not load unless a selected option binds this id".
    # The runner only loads selected bindings, so a selected id still loads.
    enabled_default: bool = True
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoraLibrary:
    """LoRA table keyed by `lora_id`. Does not open `.safetensors` files."""

    loras: dict[str, LoraEntry]
    version: int = 1

    def get(self, lora_id: str) -> LoraEntry | None:
        return self.loras.get(lora_id)


@dataclass
class LoraBinding:
    lora_id: str
    strength_model: float | None = None
    strength_clip: float | None = None


@dataclass
class ThemeOption:
    option_id: str
    label: str
    description: str
    lora_bindings: list[LoraBinding] = field(default_factory=list)


@dataclass
class ThemeDefinition:
    theme_id: str
    title: str
    instructions: str
    select_mode: str
    options: list[ThemeOption]
    none_option_id: str | None = None


@dataclass
class ThemeLibrary:
    """Theme table keyed by `theme_id`. Options cite `lora_id`, not file paths."""

    themes: dict[str, ThemeDefinition]
    version: int = 1

    def get(self, theme_id: str) -> ThemeDefinition | None:
        return self.themes.get(theme_id)


@dataclass
class WhenClause:
    step_id: str
    op: str
    option_ids: list[str] = field(default_factory=list)


@dataclass
class Action:
    type: str
    instructions: str | None = None
    select_mode: str | None = None
    keep_option_ids: list[str] | None = None
    remove_option_ids: list[str] | None = None
    add_options: list[ThemeOption] | None = None
    patch_bindings: dict[str, list[LoraBinding]] | None = None


@dataclass
class DependencyRule:
    when: WhenClause
    actions: list[Action]


@dataclass
class SequenceStep:
    step_id: str
    theme_id: str
    enabled_by_default: bool = True
    dependencies: list[DependencyRule] = field(default_factory=list)


@dataclass
class ThemeSequenceDef:
    """Sequence stored on the Theme Sequence node. Not a wire type (SPEC §1)."""

    steps: list[SequenceStep]
    version: int = 1


def parse_lora_library(source: str | dict[str, Any]) -> LoraLibrary:
    return validate_lora_library(_load_object(source, "lora library"))


def parse_theme_library(source: str | dict[str, Any]) -> ThemeLibrary:
    return validate_theme_library(_load_object(source, "theme library"))


def parse_sequence(source: str | dict[str, Any]) -> ThemeSequenceDef:
    return validate_sequence(_load_object(source, "sequence"))


def validate_lora_library(data: dict[str, Any]) -> LoraLibrary:
    path = "lora library"
    _require_object(data, path)
    _reject_unknown(data, _LORA_LIBRARY_KEYS, path)
    version = _version(data, path)
    entries = _require_list(data, "loras", path)
    loras: dict[str, LoraEntry] = {}
    for index, item in enumerate(entries):
        entry = _parse_lora_entry(item, f"{path}.loras[{index}]")
        if entry.lora_id in loras:
            raise SchemaError(f"duplicate lora_id {entry.lora_id!r}", f"{path}.loras[{index}]")
        loras[entry.lora_id] = entry
    return LoraLibrary(loras=loras, version=version)


def validate_theme_library(data: dict[str, Any]) -> ThemeLibrary:
    path = "theme library"
    _require_object(data, path)
    _reject_unknown(data, _THEME_LIBRARY_KEYS, path)
    version = _version(data, path)
    items = _require_list(data, "themes", path)
    themes: dict[str, ThemeDefinition] = {}
    for index, item in enumerate(items):
        theme = _parse_theme(item, f"{path}.themes[{index}]")
        if theme.theme_id in themes:
            raise SchemaError(
                f"duplicate theme_id {theme.theme_id!r}",
                f"{path}.themes[{index}]",
            )
        themes[theme.theme_id] = theme
    return ThemeLibrary(themes=themes, version=version)


def validate_sequence(data: dict[str, Any]) -> ThemeSequenceDef:
    path = "sequence"
    _require_object(data, path)
    _reject_unknown(data, _SEQUENCE_KEYS, path)
    version = _version(data, path)
    items = _require_list(data, "steps", path)
    steps: list[SequenceStep] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        step = _parse_step(item, f"{path}.steps[{index}]")
        if step.step_id in seen:
            raise SchemaError(f"duplicate step_id {step.step_id!r}", f"{path}.steps[{index}]")
        seen.add(step.step_id)
        steps.append(step)
    return ThemeSequenceDef(steps=steps, version=version)


def validate_refs(
    sequence: ThemeSequenceDef,
    theme_lib: ThemeLibrary,
    lora_lib: LoraLibrary,
) -> None:
    """Resolve theme_id and lora_id, and require `when.step_id` to be earlier.

    Only themes the sequence references are checked. A theme that no step uses
    can cite a LoRA this run does not load. `when.option_ids` are not checked
    against the prior theme: a rewrite may have added those ids at runtime.
    """

    seen_steps: list[str] = []
    for index, step in enumerate(sequence.steps):
        step_path = f"sequence.steps[{index}]"
        theme = theme_lib.themes.get(step.theme_id)
        if theme is None:
            raise SchemaError(
                f"theme_id {step.theme_id!r} is not in the theme library",
                step_path,
            )
        _require_bindings_known(theme.options, lora_lib, f"{step_path}.theme_id")
        known = set(seen_steps)
        for dep_index, dep in enumerate(step.dependencies):
            dep_path = f"{step_path}.dependencies[{dep_index}]"
            if dep.when.step_id not in known:
                raise SchemaError(
                    f"when.step_id {dep.when.step_id!r} must reference an earlier step",
                    f"{dep_path}.when",
                )
            for action_index, action in enumerate(dep.actions):
                action_path = f"{dep_path}.actions[{action_index}]"
                if action.add_options:
                    _require_bindings_known(action.add_options, lora_lib, action_path)
                if action.patch_bindings:
                    for option_id, bindings in action.patch_bindings.items():
                        _require_binding_ids(
                            bindings,
                            lora_lib,
                            f"{action_path}.patch_bindings.{option_id}",
                        )
        seen_steps.append(step.step_id)


def _load_object(source: str | dict[str, Any], label: str) -> dict[str, Any]:
    if isinstance(source, dict):
        return source
    if not isinstance(source, str):
        raise SchemaError(f"{label} must be a JSON object or string")
    text = source[1:] if source.startswith("\ufeff") else source
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaError(
            f"not valid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})"
        ) from exc
    _require_object(data, label)
    return data


def _parse_lora_entry(data: Any, path: str) -> LoraEntry:
    _require_object(data, path)
    _reject_unknown(data, _LORA_ENTRY_KEYS, path)
    lora_id = _require_id(data, "lora_id", path)
    name = _require_name(data, path)
    return LoraEntry(
        lora_id=lora_id,
        name=name,
        strength_model=_require_float_field(data, "strength_model", path),
        strength_clip=_require_float_field(data, "strength_clip", path),
        tags=_optional_string_list(data, "tags", path),
        enabled_default=_optional_bool(data, "enabled_default", path, default=True),
        meta=_optional_object(data, "meta", path),
    )


def _parse_theme(data: Any, path: str) -> ThemeDefinition:
    _require_object(data, path)
    _reject_unknown(data, _THEME_KEYS, path)
    theme_id = _require_id(data, "theme_id", path)
    title = _require_text(data, "title", path)
    instructions = _require_text(data, "instructions", path)
    select_mode = _require_choice(data, "select_mode", SELECT_MODES, path)
    raw_options = _require_list(data, "options", path)
    options: list[ThemeOption] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_options):
        option = _parse_option(item, f"{path}.options[{index}]", seen)
        options.append(option)
    none_id = _optional_id_or_null(data, "none_option_id", path)
    known = {option.option_id for option in options}
    if none_id is not None and none_id not in known:
        raise SchemaError(
            f"none_option_id {none_id!r} is not an option of this theme",
            path,
        )
    return ThemeDefinition(
        theme_id=theme_id,
        title=title,
        instructions=instructions,
        select_mode=select_mode,
        options=options,
        none_option_id=none_id,
    )


def _parse_option(data: Any, path: str, seen: set[str]) -> ThemeOption:
    _require_object(data, path)
    _reject_unknown(data, _OPTION_KEYS, path)
    option_id = _require_id(data, "option_id", path)
    if option_id in seen:
        raise SchemaError(f"duplicate option_id {option_id!r}", path)
    seen.add(option_id)
    raw_bindings = data.get("lora_bindings", [])
    if not isinstance(raw_bindings, list):
        raise SchemaError("lora_bindings must be a list", path)
    bindings = [
        _parse_binding(item, f"{path}.lora_bindings[{index}]")
        for index, item in enumerate(raw_bindings)
    ]
    return ThemeOption(
        option_id=option_id,
        label=_require_text(data, "label", path, allow_empty=True),
        description=_require_text(data, "description", path, allow_empty=True),
        lora_bindings=bindings,
    )


def _parse_binding(data: Any, path: str) -> LoraBinding:
    _require_object(data, path)
    _reject_unknown(data, _BINDING_KEYS, path)
    return LoraBinding(
        lora_id=_require_id(data, "lora_id", path),
        strength_model=_optional_float_field(data, "strength_model", path),
        strength_clip=_optional_float_field(data, "strength_clip", path),
    )


def _parse_step(data: Any, path: str) -> SequenceStep:
    _require_object(data, path)
    _reject_unknown(data, _STEP_KEYS, path)
    raw_deps = data.get("dependencies", [])
    if not isinstance(raw_deps, list):
        raise SchemaError("dependencies must be a list", path)
    dependencies = [
        _parse_dependency(item, f"{path}.dependencies[{index}]")
        for index, item in enumerate(raw_deps)
    ]
    return SequenceStep(
        step_id=_require_id(data, "step_id", path),
        theme_id=_require_id(data, "theme_id", path),
        enabled_by_default=_optional_bool(data, "enabled_by_default", path, default=True),
        dependencies=dependencies,
    )


def _parse_dependency(data: Any, path: str) -> DependencyRule:
    _require_object(data, path)
    _reject_unknown(data, _DEPENDENCY_KEYS, path)
    if "when" not in data:
        raise SchemaError("missing when", path)
    if "actions" not in data:
        raise SchemaError("missing actions", path)
    actions_raw = data["actions"]
    if not isinstance(actions_raw, list):
        raise SchemaError("actions must be a list", path)
    return DependencyRule(
        when=_parse_when(data["when"], f"{path}.when"),
        actions=[
            _parse_action(item, f"{path}.actions[{index}]")
            for index, item in enumerate(actions_raw)
        ],
    )


def _parse_when(data: Any, path: str) -> WhenClause:
    _require_object(data, path)
    _reject_unknown(data, _WHEN_KEYS, path)
    op = _require_choice(data, "op", WHEN_OPS, path)
    if op in WHEN_OPS_BARE:
        if "option_ids" in data and data["option_ids"] not in ([], None):
            raise SchemaError(f"op {op!r} does not take option_ids", path)
        option_ids: list[str] = []
    else:
        option_ids = _require_id_list(data, "option_ids", path, required=True)
        if op in ("eq", "neq") and len(option_ids) != 1:
            raise SchemaError(f"op {op!r} requires exactly one option_id", path)
        if op in ("includes_any", "includes_all") and len(option_ids) < 1:
            raise SchemaError(f"op {op!r} requires at least one option_id", path)
    return WhenClause(step_id=_require_id(data, "step_id", path), op=op, option_ids=option_ids)


def _parse_action(data: Any, path: str) -> Action:
    _require_object(data, path)
    if "type" not in data:
        raise SchemaError("missing type", path)
    action_type = data["type"]
    if action_type not in ACTION_TYPES:
        allowed = ", ".join(ACTION_TYPES)
        raise SchemaError(f"type must be one of: {allowed}", path)
    _reject_unknown(data, _ACTION_KEYS[action_type], path)
    action = Action(type=action_type)
    if action_type == "rewrite_instructions":
        action.instructions = _require_text(data, "instructions", path)
    elif action_type == "set_select_mode":
        action.select_mode = _require_choice(data, "select_mode", SELECT_MODES, path)
    elif action_type == "rewrite_options":
        if "keep_option_ids" in data:
            action.keep_option_ids = _require_id_list(
                data, "keep_option_ids", path, required=True
            )
        if "remove_option_ids" in data:
            action.remove_option_ids = _require_id_list(
                data, "remove_option_ids", path, required=True
            )
        if "add_options" in data:
            raw_add = data["add_options"]
            if not isinstance(raw_add, list):
                raise SchemaError("add_options must be a list", path)
            seen: set[str] = set()
            action.add_options = [
                _parse_option(item, f"{path}.add_options[{index}]", seen)
                for index, item in enumerate(raw_add)
            ]
        if "patch_bindings" in data:
            raw_patch = data["patch_bindings"]
            if not isinstance(raw_patch, dict):
                raise SchemaError("patch_bindings must be an object", path)
            patch: dict[str, list[LoraBinding]] = {}
            for option_id, raw_bindings in raw_patch.items():
                if not isinstance(option_id, str) or _has_whitespace(option_id) or option_id == "":
                    raise SchemaError(
                        "patch_bindings keys must be option ids without whitespace",
                        path,
                    )
                if not isinstance(raw_bindings, list):
                    raise SchemaError(
                        f"patch_bindings[{option_id!r}] must be a list of bindings",
                        path,
                    )
                patch[option_id] = [
                    _parse_binding(item, f"{path}.patch_bindings.{option_id}[{index}]")
                    for index, item in enumerate(raw_bindings)
                ]
            action.patch_bindings = patch
    return action


def _require_bindings_known(
    options: list[ThemeOption],
    lora_lib: LoraLibrary,
    path: str,
) -> None:
    for option in options:
        _require_binding_ids(option.lora_bindings, lora_lib, f"{path}.{option.option_id}")


def _require_binding_ids(
    bindings: list[LoraBinding],
    lora_lib: LoraLibrary,
    path: str,
) -> None:
    for binding in bindings:
        if binding.lora_id not in lora_lib.loras:
            raise SchemaError(
                f"lora_id {binding.lora_id!r} is not in the LoRA library",
                path,
            )


def _require_object(data: Any, path: str) -> None:
    if not isinstance(data, dict):
        raise SchemaError("expected a JSON object", path)


def _reject_unknown(data: dict[str, Any], allowed: set[str], path: str) -> None:
    extra = sorted(set(data) - allowed)
    if extra:
        names = ", ".join(extra)
        raise SchemaError(f"unknown field(s): {names}", path)


def _version(data: dict[str, Any], path: str) -> int:
    if "version" not in data:
        return 1
    value = data["version"]
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaError("version must be an integer", path)
    if value != 1:
        raise SchemaError(
            f"unsupported version {value}; this package supports version 1 only",
            path,
        )
    return value


def _require_list(data: dict[str, Any], key: str, path: str) -> list[Any]:
    if key not in data:
        raise SchemaError(f"missing {key}", path)
    value = data[key]
    if not isinstance(value, list):
        raise SchemaError(f"{key} must be a list", path)
    return value


def _require_text(
    data: dict[str, Any],
    key: str,
    path: str,
    *,
    allow_empty: bool = False,
) -> str:
    if key not in data:
        raise SchemaError(f"missing {key}", path)
    value = data[key]
    if not isinstance(value, str):
        raise SchemaError(f"{key} must be a string", path)
    if not allow_empty and value.strip() == "":
        raise SchemaError(f"{key} must be a non-empty string", path)
    return value


def _require_id(data: dict[str, Any], key: str, path: str) -> str:
    value = _require_text(data, key, path)
    if _has_whitespace(value):
        raise SchemaError(f"{key} must not contain whitespace", path)
    return value


def _require_name(data: dict[str, Any], path: str) -> str:
    value = _require_text(data, "name", path)
    if value != value.strip():
        raise SchemaError("name must not have leading or trailing whitespace", path)
    return value


def _require_choice(
    data: dict[str, Any],
    key: str,
    allowed: tuple[str, ...],
    path: str,
) -> str:
    value = _require_text(data, key, path)
    if value not in allowed:
        names = ", ".join(allowed)
        raise SchemaError(f"{key} must be one of: {names}", path)
    return value


def _require_float_field(data: dict[str, Any], key: str, path: str) -> float:
    if key not in data:
        raise SchemaError(f"missing {key}", path)
    return _as_float(data[key], path, key)


def _optional_float_field(data: dict[str, Any], key: str, path: str) -> float | None:
    if key not in data or data[key] is None:
        return None
    return _as_float(data[key], path, key)


def _as_float(value: Any, path: str, what: str) -> float:
    # bool is a subclass of int; reject it so `true` is not strength 1.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchemaError(f"{what} must be a number", path)
    number = float(value)
    if not math.isfinite(number):
        raise SchemaError(f"{what} must be a finite number", path)
    return number


def _optional_bool(
    data: dict[str, Any],
    key: str,
    path: str,
    *,
    default: bool,
) -> bool:
    if key not in data:
        return default
    value = data[key]
    if not isinstance(value, bool):
        raise SchemaError(f"{key} must be a boolean", path)
    return value


def _optional_object(data: dict[str, Any], key: str, path: str) -> dict[str, Any]:
    if key not in data:
        return {}
    value = data[key]
    if not isinstance(value, dict):
        raise SchemaError(f"{key} must be an object", path)
    return dict(value)


def _optional_string_list(data: dict[str, Any], key: str, path: str) -> list[str]:
    if key not in data:
        return []
    return _string_list(data[key], path, key)


def _optional_id_or_null(data: dict[str, Any], key: str, path: str) -> str | None:
    if key not in data or data[key] is None:
        return None
    value = data[key]
    if not isinstance(value, str) or value.strip() == "":
        raise SchemaError(f"{key} must be a non-empty string or null", path)
    if _has_whitespace(value):
        raise SchemaError(f"{key} must not contain whitespace", path)
    return value


def _require_id_list(
    data: dict[str, Any],
    key: str,
    path: str,
    *,
    required: bool,
) -> list[str]:
    if key not in data:
        if required:
            raise SchemaError(f"missing {key}", path)
        return []
    values = _string_list(data[key], path, key)
    for item in values:
        if _has_whitespace(item) or item == "":
            raise SchemaError(f"{key} entries must be ids without whitespace", path)
    return values


def _string_list(value: Any, path: str, key: str) -> list[str]:
    if not isinstance(value, list):
        raise SchemaError(f"{key} must be a list of strings", path)
    if not all(isinstance(item, str) for item in value):
        raise SchemaError(f"{key} must be a list of strings", path)
    return list(value)


def _has_whitespace(value: str) -> bool:
    return any(character.isspace() for character in value)
