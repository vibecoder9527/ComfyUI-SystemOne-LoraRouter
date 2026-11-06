"""Turn pre-break theme libraries and sequences into theme documents and a plan.

This module does not register nodes and does not call SystemOne. Runtime
parsing rejects ``lora_bindings`` and ``fallback_option_id``. Call these
helpers while editing JSON, then store the results on Theme nodes.

Per-option strength overrides are dropped. LoRA Aggregate uses the library
strengths. ``rewrite_*`` and ``disable_step`` are warnings, not behavior.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .theme_ids import ensure_theme_document
from .types import SchemaError, parse_enable_rules, parse_theme

_WHEN_OPS = ("eq", "neq", "includes_any", "includes_all", "skipped", "answered")
_BARE_OPS = ("skipped", "answered")


@dataclass
class MigratedTheme:
    """A theme document that ``parse_theme`` accepts, plus human-readable notes."""

    document: dict[str, Any]
    notes: list[str] = field(default_factory=list)


def migrate_theme_library(source: str | dict[str, Any]) -> list[MigratedTheme]:
    """Migrate every theme in an old library, or wrap one theme object."""

    data = _load(source, "theme migration")
    if "themes" in data:
        themes = data["themes"]
        if not isinstance(themes, list):
            raise SchemaError("themes must be a list", "theme migration")
        return [_migrate_theme(item, f"themes[{index}]") for index, item in enumerate(themes)]
    if "theme_id" in data or "options" in data:
        return [_migrate_theme(data, "theme")]
    raise SchemaError(
        "expected a theme object or a library with a themes list",
        "theme migration",
    )


def migrate_theme_document(source: str | dict[str, Any]) -> MigratedTheme:
    """Migrate one theme. A library with any other count is rejected."""

    migrated = migrate_theme_library(source)
    if len(migrated) != 1:
        raise SchemaError(
            f"migrate_theme_document expected one theme, found {len(migrated)}; "
            "use migrate_theme_library",
            "theme migration",
        )
    return migrated[0]


def retag_lora_library(
    library: str | dict[str, Any],
    theme_documents: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Copy option tags that equal a ``lora_id`` onto that library entry.

    Other tags are left untouched. Strengths and manual ids are not rewritten.
    The returned library is a new dict.
    """

    data = _load(library, "lora library")
    if not isinstance(data.get("loras"), list):
        raise SchemaError("loras must be a list", "lora library")
    wanted: set[str] = set()
    for theme in theme_documents:
        if not isinstance(theme, dict):
            raise SchemaError("theme documents must be objects", "retag")
        for option in theme.get("options") or []:
            if not isinstance(option, dict):
                continue
            for tag in option.get("tags") or []:
                if isinstance(tag, str) and tag:
                    wanted.add(tag)
    notes: list[str] = []
    loras: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for entry in data["loras"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("lora_id"), str):
            raise SchemaError("each lora entry needs a lora_id", "lora library")
        lora_id = entry["lora_id"]
        if lora_id in seen_ids:
            raise SchemaError(f"duplicate lora_id {lora_id!r}", "lora library")
        seen_ids.add(lora_id)
        copy = dict(entry)
        tags = list(copy.get("tags") or [])
        if not isinstance(copy.get("tags", []), list):
            raise SchemaError(f"tags on {lora_id!r} must be a list", "lora library")
        if lora_id in wanted and lora_id not in tags:
            tags.append(lora_id)
            notes.append(f"added tag {lora_id!r} to lora_id {lora_id!r}")
            copy["tags"] = tags
        loras.append(copy)
    unused = sorted(tag for tag in wanted if tag not in seen_ids)
    for tag in unused:
        notes.append(f"tag {tag!r} does not match a lora_id, so no library entry was retagged")
    out = dict(data)
    out["loras"] = loras
    return out, notes


def plan_sequence(source: str | dict[str, Any]) -> dict[str, Any]:
    """Advisory Theme-node plan for an old ``sequence_json``.

    The plan is not executed. ``enabled_by_default: true`` with no
    ``disable_step`` becomes ``run: enabled``. A step that starts disabled
    becomes ``when_upstream``, and each ``enable_step`` dependency becomes a
    clause whose ``theme_id`` is the referenced step's theme. Old ``step_id``
    values are not enable targets.
    """

    data = _load(source, "sequence")
    steps = data.get("steps")
    if not isinstance(steps, list):
        raise SchemaError("steps must be a list", "sequence")
    step_theme: dict[str, str] = {}
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise SchemaError("step must be an object", f"sequence.steps[{index}]")
        step_id = step.get("step_id")
        theme_id = step.get("theme_id")
        if not isinstance(step_id, str) or not step_id or any(ch.isspace() for ch in step_id):
            raise SchemaError("step_id must be an id", f"sequence.steps[{index}]")
        if not isinstance(theme_id, str) or not theme_id or any(ch.isspace() for ch in theme_id):
            raise SchemaError("theme_id must be an id", f"sequence.steps[{index}]")
        if step_id in step_theme:
            raise SchemaError(f"duplicate step_id {step_id!r}", f"sequence.steps[{index}]")
        step_theme[step_id] = theme_id

    nodes: list[dict[str, Any]] = []
    warnings: list[str] = []
    theme_counts: dict[str, int] = {}
    for theme_id in step_theme.values():
        theme_counts[theme_id] = theme_counts.get(theme_id, 0) + 1
    for theme_id, count in theme_counts.items():
        if count > 1:
            warnings.append(
                f"theme_id {theme_id!r} is used by {count} steps; a result chain requires unique theme ids"
            )

    for index, step in enumerate(steps):
        step_warnings: list[str] = []
        clauses: list[dict[str, Any]] = []
        saw_disable = False
        saw_enable = False
        for dep_index, dep in enumerate(step.get("dependencies") or []):
            path = f"sequence.steps[{index}].dependencies[{dep_index}]"
            if not isinstance(dep, dict):
                raise SchemaError("dependency must be an object", path)
            actions = dep.get("actions") or []
            if not isinstance(actions, list):
                raise SchemaError("actions must be a list", path)
            types = []
            for action in actions:
                if isinstance(action, dict) and isinstance(action.get("type"), str):
                    types.append(action["type"])
            if "disable_step" in types:
                saw_disable = True
                step_warnings.append(
                    "disable_step has no equivalent; this plan does not turn the theme off conditionally"
                )
            for action_type in types:
                if action_type in ("rewrite_options", "rewrite_instructions", "set_select_mode"):
                    step_warnings.append(
                        f"{action_type} is not migrated; edit the Theme document by hand"
                    )
            if "enable_step" in types:
                saw_enable = True
                clause = _clause_from_when(dep.get("when"), step_theme, path, step_warnings)
                if clause is not None:
                    clauses.append(clause)
        enabled_default = step.get("enabled_by_default", True)
        if not isinstance(enabled_default, bool):
            raise SchemaError(
                "enabled_by_default must be a boolean",
                f"sequence.steps[{index}]",
            )
        if enabled_default and not saw_disable:
            run = "enabled"
            if clauses:
                step_warnings.append(
                    "enabled_by_default was true, so run is enabled; "
                    "the enable clauses are not required to turn this theme on"
                )
            enable_json = {"version": 1, "match": "any", "clauses": []}
        elif saw_enable:
            run = "when_upstream"
            enable_json = {"version": 1, "match": "any", "clauses": clauses}
        else:
            run = "disabled"
            enable_json = {"version": 1, "match": "any", "clauses": []}
            if not enabled_default:
                step_warnings.append(
                    "the step started disabled and had no enable_step action, so run is disabled"
                )
        parse_enable_rules(enable_json)
        nodes.append(
            {
                "step_id": step["step_id"],
                "theme_id": step["theme_id"],
                "run": run,
                "enable_json": enable_json,
                "warnings": step_warnings,
            }
        )
    return {
        "nodes": nodes,
        "warnings": warnings,
        "removed": [
            "S1ThemeLibrary",
            "S1ThemeSequence",
            "lora_bindings",
            "fallback_option_id",
            "strength_conflict",
            "sequence_json",
        ],
    }


def _migrate_theme(data: Any, path: str) -> MigratedTheme:
    if not isinstance(data, dict):
        raise SchemaError("theme must be an object", path)
    notes: list[str] = []
    if "fallback_option_id" in data and data["fallback_option_id"] not in (None, ""):
        notes.append(
            f"fallback_option_id {data['fallback_option_id']!r} was removed and is not applied"
        )
    elif "fallback_option_id" in data:
        notes.append("fallback_option_id was removed and is not applied")
    options = data.get("options", [])
    if not isinstance(options, list):
        raise SchemaError("options must be a list", path)
    new_options = []
    for index, option in enumerate(options):
        new_options.append(_migrate_option(option, f"{path}.options[{index}]", notes))
    document: dict[str, Any] = {
        "version": 1,
        "theme_id": data.get("theme_id", ""),
        "title": data.get("title", ""),
        "instructions": data.get("instructions", ""),
        "select_mode": data.get("select_mode", ""),
        "options": new_options,
    }
    if data.get("none_option_id"):
        document["none_option_id"] = data["none_option_id"]
    filled = ensure_theme_document(document)
    parse_theme(filled)
    return MigratedTheme(document=filled, notes=notes)


def _migrate_option(data: Any, path: str, notes: list[str]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise SchemaError("option must be an object", path)
    bindings = data.get("lora_bindings", [])
    if bindings is None:
        bindings = []
    if not isinstance(bindings, list):
        raise SchemaError("lora_bindings must be a list", path)
    tags = data.get("tags")
    if tags is None:
        tags = []
    if not isinstance(tags, list) or not all(isinstance(item, str) for item in tags):
        raise SchemaError("tags must be a list of strings", path)
    bound_ids: list[str] = []
    saw_override = False
    for index, binding in enumerate(bindings):
        if not isinstance(binding, dict) or not isinstance(binding.get("lora_id"), str):
            raise SchemaError("binding needs a lora_id", f"{path}.lora_bindings[{index}]")
        lora_id = binding["lora_id"]
        if lora_id not in bound_ids:
            bound_ids.append(lora_id)
        if binding.get("strength_model") is not None or binding.get("strength_clip") is not None:
            saw_override = True
    if bindings and tags:
        notes.append(
            f"{path}: kept existing tags and dropped lora_bindings {bound_ids}"
        )
        used = list(tags)
    elif bindings:
        used = bound_ids
        notes.append(
            f"{path}: tags were filled from lora_id values {bound_ids}; "
            "retag the LoRA library with those ids or set matching tags by hand"
        )
    else:
        used = list(tags)
    if saw_override:
        notes.append(
            f"{path}: dropped per-binding strengths; aggregate uses the library strength"
        )
    option = {
        "option_id": data.get("option_id", ""),
        "label": data.get("label", ""),
        "description": data.get("description", ""),
    }
    if used:
        option["tags"] = used
    return option


def _clause_from_when(when: Any, step_theme: dict[str, str], path: str, warnings: list[str]):
    if not isinstance(when, dict):
        raise SchemaError("when must be an object", path)
    op = when.get("op")
    step_id = when.get("step_id")
    if op not in _WHEN_OPS:
        warnings.append(f"{path}: skipped unrecognized when.op {op!r}")
        return None
    if not isinstance(step_id, str) or step_id not in step_theme:
        warnings.append(f"{path}: when.step_id {step_id!r} does not map to a theme_id")
        return None
    clause: dict[str, Any] = {"theme_id": step_theme[step_id], "op": op}
    if op not in _BARE_OPS:
        option_ids = when.get("option_ids")
        if not isinstance(option_ids, list) or not option_ids:
            warnings.append(f"{path}: {op} needs option_ids and was not copied")
            return None
        clause["option_ids"] = list(option_ids)
    return clause


def _load(source: str | dict[str, Any], label: str) -> dict[str, Any]:
    if isinstance(source, dict):
        return source
    if not isinstance(source, str):
        raise SchemaError(f"{label} must be a JSON object or string")
    text = source[1:] if source.startswith("\ufeff") else source
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaError(f"not valid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise SchemaError(f"{label} must be a JSON object")
    return data


__all__ = [
    "MigratedTheme",
    "migrate_theme_document",
    "migrate_theme_library",
    "plan_sequence",
    "retag_lora_library",
]
