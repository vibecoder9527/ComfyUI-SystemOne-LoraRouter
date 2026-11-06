"""Dataclasses and validators for LoRA libraries, one theme, and enable rules.

Version defaults to 1 when the field is omitted. A theme document is one theme,
not a library. Options carry tags. They do not carry ``lora_bindings``.
``fallback_option_id`` is rejected.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

# Widget defaults. Dynamic prompts must stay off so the braces stay literal JSON.
EMPTY_LORA_LIBRARY_JSON = '{ "loras": [] }'
EMPTY_THEME_JSON = (
    '{ "version": 1, "theme_id": "theme_1", "title": "Theme", '
    '"instructions": "Choose the options that fit the prompt.", '
    '"select_mode": "single", "options": [] }'
)
EMPTY_ENABLE_JSON = '{ "match": "any", "clauses": [] }'

SELECT_MODES = ("single", "multi")
RUN_MODES = ("disabled", "enabled", "when_upstream")
ENABLE_MATCH = ("any", "all")
ENABLE_OPS_WITH_OPTIONS = ("eq", "neq", "includes_any", "includes_all")
ENABLE_OPS_BARE = ("skipped", "answered")
ENABLE_OPS = ENABLE_OPS_WITH_OPTIONS + ENABLE_OPS_BARE

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
_THEME_KEYS = {
    "version",
    "theme_id",
    "title",
    "instructions",
    "select_mode",
    "options",
    "none_option_id",
}
_OPTION_KEYS = {"option_id", "label", "description", "tags"}
_ENABLE_KEYS = {"version", "match", "clauses"}
_CLAUSE_KEYS = {"theme_id", "op", "option_ids"}

_REMOVED_THEME_FIELDS = {
    "fallback_option_id": "fallback_option_id was removed and is not applied",
    "themes": "a theme node stores one theme; a library of themes is not accepted",
    "lora_bindings": "lora_bindings was removed; selected options contribute tags",
}
_REMOVED_OPTION_FIELDS = {
    "lora_bindings": "lora_bindings was removed; selected options contribute tags",
    "fallback_option_id": "fallback_option_id was removed and is not applied",
}


class SchemaError(ValueError):
    """Invalid library, theme, or enable JSON. `path` locates the field."""

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
    # False: aggregate skips this entry even when a selected tag matches.
    enabled_default: bool = True
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoraLibrary:
    """LoRA table keyed by `lora_id`. Does not open weight files."""

    loras: dict[str, LoraEntry]
    version: int = 1

    def get(self, lora_id: str) -> LoraEntry | None:
        return self.loras.get(lora_id)


@dataclass
class ThemeOption:
    option_id: str
    label: str
    description: str
    tags: list[str] = field(default_factory=list)


@dataclass
class ThemeDefinition:
    """One theme. `none_option_id` contributes no tags when it is selected."""

    theme_id: str
    title: str
    instructions: str
    select_mode: str
    options: list[ThemeOption]
    none_option_id: str | None = None
    version: int = 1


@dataclass
class EnableClause:
    theme_id: str
    op: str
    option_ids: list[str] = field(default_factory=list)


@dataclass
class EnableRules:
    """How a downstream theme reads an upstream ``S1_THEME_RESULT``.

    ``match`` is ``any`` (OR) or ``all`` (AND). An empty clause list matches
    nothing, so ``when_upstream`` stays off until a clause is stored.
    """

    clauses: list[EnableClause] = field(default_factory=list)
    match: str = "any"
    version: int = 1


@dataclass
class ThemeDecision:
    """One theme's outcome inside an accumulated result.

    ``status`` is ``ok``, ``skipped``, or ``error``. ``enabled`` is true when
    this theme was allowed to decide (including a failed call). Option ops
    match only ``status == ok``. ``option_tags`` is ``(option_id, tags)`` for
    options that contributed tags, in option order. The ``none`` option is
    omitted there even if it was selected.
    """

    theme_id: str
    status: str
    enabled: bool
    selected: list[str]
    tags: list[str]
    select_mode: str
    option_tags: list[tuple[str, list[str]]] = field(default_factory=list)
    raw: dict[str, Any] | None = None
    error: str | None = None
    reason: str | None = None


@dataclass
class ThemeResult:
    """Accumulated decisions. ``tags`` is the first-seen union of ok decisions."""

    decisions: list[ThemeDecision] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    version: int = 1

    def get(self, theme_id: str) -> ThemeDecision | None:
        for decision in self.decisions:
            if decision.theme_id == theme_id:
                return decision
        return None


def parse_lora_library(source: str | dict[str, Any]) -> LoraLibrary:
    return validate_lora_library(_load_object(source, "lora library"))


def parse_theme(source: str | dict[str, Any]) -> ThemeDefinition:
    return validate_theme(_load_object(source, "theme"))


def parse_enable_rules(source: str | dict[str, Any]) -> EnableRules:
    return validate_enable_rules(_load_object(source, "enable"))


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


def validate_theme(data: dict[str, Any]) -> ThemeDefinition:
    path = "theme"
    _require_object(data, path)
    _reject_removed(data, _REMOVED_THEME_FIELDS, path)
    _reject_unknown(data, _THEME_KEYS, path)
    version = _version(data, path)
    theme_id = _require_id(data, "theme_id", path)
    raw_options = _require_list(data, "options", path)
    options: list[ThemeOption] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_options):
        options.append(_parse_option(item, f"{path}.options[{index}]", seen))
    none_id = _optional_id_or_null(data, "none_option_id", path)
    known = {option.option_id for option in options}
    if none_id is not None and none_id not in known:
        raise SchemaError(
            f"none_option_id {none_id!r} is not an option of this theme",
            path,
        )
    return ThemeDefinition(
        theme_id=theme_id,
        title=_require_text(data, "title", path),
        instructions=_require_text(data, "instructions", path),
        select_mode=_require_choice(data, "select_mode", SELECT_MODES, path),
        options=options,
        none_option_id=none_id,
        version=version,
    )


def validate_enable_rules(data: dict[str, Any]) -> EnableRules:
    path = "enable"
    _require_object(data, path)
    _reject_unknown(data, _ENABLE_KEYS, path)
    version = _version(data, path)
    match = "any"
    if "match" in data:
        match = _require_choice(data, "match", ENABLE_MATCH, path)
    raw_clauses = data.get("clauses", [])
    if not isinstance(raw_clauses, list):
        raise SchemaError("clauses must be a list", path)
    clauses = [
        _parse_clause(item, f"{path}.clauses[{index}]")
        for index, item in enumerate(raw_clauses)
    ]
    return EnableRules(clauses=clauses, match=match, version=version)


def empty_theme_result() -> ThemeResult:
    return ThemeResult(decisions=[], tags=[], errors=[])


def build_theme_result(
    decisions: list[ThemeDecision],
    errors: list[str] | None = None,
) -> ThemeResult:
    """Copy `decisions` into a result. Duplicate ``theme_id`` is an error.

    Tags come from decisions whose status is ``ok``, first-seen order.
    """

    seen_ids: set[str] = set()
    tags: list[str] = []
    seen_tags: set[str] = set()
    copied: list[ThemeDecision] = []
    for decision in decisions:
        if not isinstance(decision, ThemeDecision):
            raise SchemaError("theme result decisions must be ThemeDecision values")
        if decision.theme_id in seen_ids:
            raise SchemaError(
                f"duplicate theme_id {decision.theme_id!r} in the theme result"
            )
        seen_ids.add(decision.theme_id)
        copied.append(decision)
        if decision.status != "ok":
            continue
        for tag in decision.tags:
            if tag not in seen_tags:
                seen_tags.add(tag)
                tags.append(tag)
    return ThemeResult(decisions=copied, tags=tags, errors=list(errors or []))


def public_decision(decision: ThemeDecision) -> dict[str, Any]:
    """JSON-ready decision. ``option_tags`` stays on the Python object."""

    payload: dict[str, Any] = {
        "theme_id": decision.theme_id,
        "status": decision.status,
        "enabled": decision.enabled,
        "selected": list(decision.selected),
        "tags": list(decision.tags),
        "select_mode": decision.select_mode,
    }
    if decision.reason:
        payload["reason"] = decision.reason
    if decision.error:
        payload["error"] = decision.error
    if decision.raw is not None:
        payload["raw"] = decision.raw
    return payload


def _parse_lora_entry(data: Any, path: str) -> LoraEntry:
    _require_object(data, path)
    _reject_unknown(data, _LORA_ENTRY_KEYS, path)
    return LoraEntry(
        lora_id=_require_id(data, "lora_id", path),
        name=_require_name(data, path),
        strength_model=_require_float_field(data, "strength_model", path),
        strength_clip=_require_float_field(data, "strength_clip", path),
        tags=_optional_string_list(data, "tags", path),
        enabled_default=_optional_bool(data, "enabled_default", path, default=True),
        meta=_optional_object(data, "meta", path),
    )


def _parse_option(data: Any, path: str, seen: set[str]) -> ThemeOption:
    _require_object(data, path)
    _reject_removed(data, _REMOVED_OPTION_FIELDS, path)
    _reject_unknown(data, _OPTION_KEYS, path)
    option_id = _require_id(data, "option_id", path)
    if option_id in seen:
        raise SchemaError(f"duplicate option_id {option_id!r}", path)
    seen.add(option_id)
    return ThemeOption(
        option_id=option_id,
        label=_require_text(data, "label", path, allow_empty=True),
        description=_require_text(data, "description", path, allow_empty=True),
        tags=_optional_string_list(data, "tags", path),
    )


def _parse_clause(data: Any, path: str) -> EnableClause:
    _require_object(data, path)
    _reject_unknown(data, _CLAUSE_KEYS, path)
    op = _require_choice(data, "op", ENABLE_OPS, path)
    if op in ENABLE_OPS_BARE:
        if "option_ids" in data and data["option_ids"] not in ([], None):
            raise SchemaError(f"op {op!r} does not take option_ids", path)
        option_ids: list[str] = []
    else:
        option_ids = _require_id_list(data, "option_ids", path, required=True)
        if op in ("eq", "neq") and len(option_ids) != 1:
            raise SchemaError(f"op {op!r} requires exactly one option_id", path)
        if op in ("includes_any", "includes_all") and len(option_ids) < 1:
            raise SchemaError(f"op {op!r} requires at least one option_id", path)
    return EnableClause(
        theme_id=_require_id(data, "theme_id", path),
        op=op,
        option_ids=option_ids,
    )


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


def _require_object(data: Any, path: str) -> None:
    if not isinstance(data, dict):
        raise SchemaError("expected a JSON object", path)


def _reject_removed(data: dict[str, Any], removed: dict[str, str], path: str) -> None:
    for key, message in removed.items():
        if key in data:
            raise SchemaError(message, path)


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
