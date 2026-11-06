"""Offline migration. This module does not register nodes or call SystemOne.

``migrate_theme_library`` turns a pre-51f1904 theme library into theme
documents. ``plan_sequence`` turns an old sequence into Theme Root plus
option wires. ``migrate_router_graph`` turns a 51f1904 Theme graph
(``run``, ``enable_json``, ``theme_result``, per-theme API widgets) into
SystemOne Settings, Theme Root, and option-slot wires.

Runtime parsing rejects ``lora_bindings`` and ``fallback_option_id``.
Per-option strength overrides are dropped. ``rewrite_*`` and ``disable_step``
are warnings, not behavior.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .theme_ids import ensure_theme_document
from .types import (
    MAX_OPTION_OUTPUTS,
    REPORT_OUTPUT_INDEX,
    EnableRules,
    SchemaError,
    parse_enable_rules,
    parse_theme,
)

_SETTINGS_FIELDS = (
    "api_key",
    "api_model",
    "endpoint",
    "noul_threshold",
    "on_error",
    "min_confidence",
)
_REMOVED_ROUTER = [
    "run",
    "enable_json",
    "theme_result",
    "S1_THEME_RESULT",
    "Theme api_key widget",
    "Theme api_model widget",
    "Theme endpoint widget",
    "Theme noul_threshold widget",
    "Theme on_error widget",
    "Theme min_confidence widget",
]

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
    """Advisory plan for an old ``sequence_json``.

    The plan is not executed. A step that starts enabled and has no
    ``disable_step`` becomes ``S1ThemeRoot``. A step that starts disabled and
    has an ``enable_step`` action becomes ``S1Theme``, and a single option
    clause becomes ``upstream_wire``. Old ``step_id`` values are not wire
    targets. ``run`` and ``enable_json`` are not emitted.
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
        rules = parse_enable_rules({"version": 1, "match": "any", "clauses": clauses})
        if enabled_default and not saw_disable:
            class_type = "S1ThemeRoot"
            dropped = False
            upstream_wire = None
            if clauses:
                step_warnings.append(
                    "enabled_by_default was true, so this node is Theme Root; "
                    "enable clauses are not wires on a root"
                )
        elif saw_enable:
            class_type = "S1Theme"
            dropped = False
            upstream_wire, wire_warnings = _option_wire(rules)
            step_warnings.extend(wire_warnings)
        else:
            class_type = None
            dropped = True
            upstream_wire = None
            if saw_disable:
                step_warnings.append(
                    "disable_step has no option-slot equivalent, so this node is omitted"
                )
            elif not enabled_default:
                step_warnings.append(
                    "the step started disabled and had no enable_step action, so it is omitted"
                )
        nodes.append(
            {
                "step_id": step["step_id"],
                "theme_id": step["theme_id"],
                "class_type": class_type,
                "dropped": dropped,
                "upstream_wire": upstream_wire,
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
            "run",
            "enable_json",
            "theme_result",
            "S1_THEME_RESULT",
        ],
    }


def _option_wire(rules: EnableRules) -> tuple[dict[str, Any] | None, list[str]]:
    """Map one enable-rule clause to a parent option slot.

    A downstream theme has one ``upstream`` socket. Several clauses, or a
    clause that names more than one option, cannot be one wire.
    """

    warnings: list[str] = []
    if not rules.clauses:
        warnings.append("no enable clause mapped to an option slot")
        return None, warnings
    if len(rules.clauses) != 1:
        warnings.append(
            "multiple enable clauses are not one upstream socket; "
            "duplicate this theme once per option slot"
        )
        return None, warnings
    clause = rules.clauses[0]
    if clause.op in ("eq", "includes_any") and len(clause.option_ids) == 1:
        return (
            {
                "theme_id": clause.theme_id,
                "option_id": clause.option_ids[0],
                "op": clause.op,
            },
            warnings,
        )
    if clause.op == "includes_any" and len(clause.option_ids) > 1:
        warnings.append(
            f"includes_any {clause.option_ids} needs one Theme copy per option; "
            "one upstream socket cannot OR those slots"
        )
        return None, warnings
    if clause.op == "includes_all":
        warnings.append(
            "includes_all is not one option slot; each selected slot already "
            "carries every tag from that multi decision"
        )
        return None, warnings
    warnings.append(f"op {clause.op!r} does not map to an option slot")
    return None, warnings


def migrate_router_graph(source: str | dict[str, Any]) -> dict[str, Any]:
    """Plan Settings + Theme Root + option wires from a 51f1904 router.

    Accepts a ComfyUI API prompt (``id -> {class_type, inputs}``) or
    ``{"nodes": [ ... ]}`` with either that shape or flat widget fields.
    The result is a plan. It is not a workflow you can queue unchanged:
    positive and negative are sockets, and option links use the new indexes.

    The API key is copied onto the settings node so you can paste it. It is
    not repeated in warnings.
    """

    raw_nodes = _router_nodes(_load(source, "router graph"))
    themes = [node for node in raw_nodes if node["class_type"] == "S1Theme"]
    by_id = {node["id"]: node for node in raw_nodes}
    option_index, theme_ids = _option_indexes(themes)
    # Dropped themes (disabled, or an unknown run mode) do not need a settings node.
    live_themes = [
        node
        for node in themes
        if node["inputs"].get("run", "disabled") in ("enabled", "when_upstream")
    ]
    settings_nodes, settings_of = _settings_nodes(live_themes)
    planned: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    warnings: list[str] = []
    wires: list[dict[str, Any]] = []

    for node in raw_nodes:
        kind = node["class_type"]
        if kind == "S1Theme":
            converted, theme_warnings, theme_wires = _convert_theme(
                node, option_index, theme_ids, settings_of
            )
            warnings.extend(theme_warnings)
            wires.extend(theme_wires)
            if converted is None:
                dropped.append(
                    {
                        "id": node["id"],
                        "reason": theme_warnings[-1] if theme_warnings else "omitted",
                    }
                )
            else:
                planned.append(converted)
            continue
        if kind == "S1LoraAggregate":
            planned.append(_convert_aggregate(node, warnings))
            continue
        if kind == "S1ThemeCollect":
            planned.append(_convert_collect(node, by_id, warnings))
            continue
        if kind in ("S1LoraLibrary", "S1Settings", "S1ThemeRoot"):
            planned.append(
                {
                    "id": node["id"],
                    "class_type": kind,
                    "inputs": dict(node["inputs"]),
                }
            )
            continue
        planned.append(
            {
                "id": node["id"],
                "class_type": kind,
                "inputs": dict(node["inputs"]),
            }
        )
        warnings.append(f"node {node['id']!r} ({kind}) was copied unchanged")

    return {
        "settings_nodes": settings_nodes,
        "nodes": planned,
        "wires": wires,
        "dropped": dropped,
        "warnings": warnings,
        "removed": list(_REMOVED_ROUTER),
        "limits": {
            "max_option_outputs": MAX_OPTION_OUTPUTS,
            "report_output_index": REPORT_OUTPUT_INDEX,
        },
    }


def _router_nodes(data: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(data.get("nodes"), list):
        nodes = []
        for index, item in enumerate(data["nodes"]):
            if not isinstance(item, dict):
                raise SchemaError("node must be an object", f"router graph.nodes[{index}]")
            node_id = item.get("id", str(index))
            if not isinstance(node_id, str) or not node_id:
                raise SchemaError("node id must be a string", f"router graph.nodes[{index}]")
            if isinstance(item.get("inputs"), dict) and isinstance(item.get("class_type"), str):
                nodes.append(
                    {
                        "id": node_id,
                        "class_type": item["class_type"],
                        "inputs": dict(item["inputs"]),
                    }
                )
                continue
            class_type = item.get("class_type", "S1Theme")
            if not isinstance(class_type, str):
                raise SchemaError("class_type must be a string", f"router graph.nodes[{index}]")
            inputs = {
                key: value
                for key, value in item.items()
                if key not in ("id", "class_type")
            }
            nodes.append({"id": node_id, "class_type": class_type, "inputs": inputs})
        return nodes
    nodes = []
    for node_id, item in data.items():
        if not isinstance(item, dict) or "class_type" not in item:
            raise SchemaError(
                "expected a nodes list or a ComfyUI API prompt",
                "router graph",
            )
        inputs = item.get("inputs", {})
        if not isinstance(inputs, dict):
            raise SchemaError("inputs must be an object", f"router graph.{node_id}")
        nodes.append({"id": str(node_id), "class_type": item["class_type"], "inputs": dict(inputs)})
    return nodes


def _option_indexes(
    themes: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, int]], dict[str, str]]:
    indexes: dict[str, dict[str, int]] = {}
    theme_ids: dict[str, str] = {}
    for node in themes:
        raw = node["inputs"].get("theme_json")
        if raw is None:
            continue
        try:
            theme = parse_theme(raw)
        except SchemaError:
            continue
        indexes[node["id"]] = {
            option.option_id: index for index, option in enumerate(theme.options)
        }
        theme_ids[node["id"]] = theme.theme_id
    return indexes, theme_ids


def _settings_from_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    endpoint = inputs.get("endpoint") or "https://system-one.dev/v1/systemone"
    return {
        "api_key": inputs.get("api_key", "") if isinstance(inputs.get("api_key", ""), str) else "",
        "api_model": inputs.get("api_model", "") if isinstance(inputs.get("api_model", ""), str) else "",
        "endpoint": endpoint if isinstance(endpoint, str) else "https://system-one.dev/v1/systemone",
        "noul_threshold": inputs.get("noul_threshold", 0.5),
        "on_error": inputs.get("on_error", "passthrough"),
        "min_confidence": inputs.get("min_confidence", 0.0),
    }


def _settings_key(settings: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(settings[field] for field in _SETTINGS_FIELDS)


def _settings_nodes(
    themes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    groups: list[tuple[tuple[Any, ...], dict[str, Any], list[str]]] = []
    for node in themes:
        settings = _settings_from_inputs(node["inputs"])
        key = _settings_key(settings)
        placed = False
        for existing in groups:
            if existing[0] == key:
                existing[2].append(node["id"])
                placed = True
                break
        if not placed:
            groups.append((key, settings, [node["id"]]))
    nodes = []
    owner: dict[str, str] = {}
    for index, (_key, settings, members) in enumerate(groups):
        node_id = "settings" if index == 0 else f"settings_{index + 1}"
        nodes.append(
            {
                "id": node_id,
                "class_type": "S1Settings",
                "inputs": settings,
                "from_nodes": members,
            }
        )
        for member in members:
            owner[member] = node_id
    return nodes, owner


def _link_node_id(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    if (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], (int, float))
    ):
        return value[0]
    return None


def _convert_theme(node, option_index, theme_ids, settings_of):
    warnings: list[str] = []
    wires: list[dict[str, Any]] = []
    inputs = node["inputs"]
    run = inputs.get("run", "disabled")
    enable_raw = inputs.get("enable_json", {"clauses": []})
    rules = None
    try:
        rules = parse_enable_rules(enable_raw if enable_raw is not None else {"clauses": []})
    except SchemaError as exc:
        warnings.append(f"node {node['id']!r}: enable_json was not usable ({exc})")
    theme_inputs: dict[str, Any] = {}
    if "positive" in inputs:
        theme_inputs["positive"] = inputs.get("positive", "")
    if "negative" in inputs:
        theme_inputs["negative"] = inputs.get("negative", "")
    # Positive is recorded before negative. Both are sockets in the new graph.
    if "positive" not in theme_inputs:
        theme_inputs = {"positive": "", **theme_inputs}
    if "negative" not in theme_inputs:
        ordered = {}
        if "positive" in theme_inputs:
            ordered["positive"] = theme_inputs.pop("positive")
        ordered["negative"] = ""
        ordered.update(theme_inputs)
        theme_inputs = ordered
    if "theme_json" in inputs:
        theme_inputs["theme_json"] = inputs["theme_json"]
    settings_id = settings_of.get(node["id"])
    if settings_id:
        theme_inputs["settings"] = [settings_id, 0]
    warnings.append(
        f"node {node['id']!r}: positive and negative are input sockets. "
        "The plan keeps the old widget text, positive first."
    )
    if run == "enabled":
        if rules is not None and rules.clauses:
            warnings.append(
                f"node {node['id']!r}: run was enabled, so enable_json is ignored"
            )
        return (
            {
                "id": node["id"],
                "class_type": "S1ThemeRoot",
                "inputs": theme_inputs,
                "option_outputs": _option_output_list(node, option_index),
            },
            warnings,
            wires,
        )
    if run == "disabled":
        warnings.append(
            f"node {node['id']!r}: run was disabled, so the node is omitted"
        )
        return None, warnings, wires
    if run != "when_upstream":
        warnings.append(f"node {node['id']!r}: run {run!r} is not a known mode, so the node is omitted")
        return None, warnings, wires
    upstream_wire = None
    if rules is not None:
        upstream_wire, wire_warnings = _option_wire(rules)
        for item in wire_warnings:
            warnings.append(f"node {node['id']!r}: {item}")
    parent_id = _link_node_id(inputs.get("upstream"))
    if upstream_wire is not None:
        slot = _resolve_slot(parent_id, upstream_wire, option_index, theme_ids)
        if slot is None:
            warnings.append(
                f"node {node['id']!r}: could not place option {upstream_wire['option_id']!r} "
                f"on upstream {parent_id!r}. Wire upstream by hand."
            )
        else:
            theme_inputs["upstream"] = [parent_id, slot]
            wires.append(
                {
                    "from": parent_id,
                    "option_id": upstream_wire["option_id"],
                    "output_index": slot,
                    "to": node["id"],
                    "input": "upstream",
                }
            )
    elif parent_id:
        warnings.append(
            f"node {node['id']!r}: upstream link {inputs.get('upstream')!r} "
            "was theme_result. Pick the parent option slot yourself."
        )
    return (
        {
            "id": node["id"],
            "class_type": "S1Theme",
            "inputs": theme_inputs,
            "upstream_wire": upstream_wire,
            "option_outputs": _option_output_list(node, option_index),
        },
        warnings,
        wires,
    )


def _option_output_list(node, option_index) -> list[dict[str, Any]]:
    slots = option_index.get(node["id"])
    if not slots:
        return []
    listed = []
    for option_id, index in slots.items():
        if option_id == "__theme_id__" or not isinstance(index, int):
            continue
        listed.append({"option_id": option_id, "index": index})
    listed.sort(key=lambda item: item["index"])
    return listed


def _resolve_slot(parent_id, wire, option_index, theme_ids) -> int | None:
    if not parent_id or parent_id not in option_index:
        return None
    parent_theme = theme_ids.get(parent_id)
    if parent_theme and parent_theme != wire["theme_id"]:
        return None
    index = option_index[parent_id].get(wire["option_id"])
    if isinstance(index, int):
        return index
    return None


def _convert_aggregate(node, warnings: list[str]) -> dict[str, Any]:
    inputs = dict(node["inputs"])
    old = inputs.pop("theme_result", None)
    if old is not None:
        warnings.append(
            f"node {node['id']!r}: LoRA Aggregate input theme_result ({old!r}) was removed. "
            "Connect decision to the option slot whose tags should be applied. "
            "Output 0 is no longer the whole theme result."
        )
    inputs.pop("enable_json", None)
    inputs.pop("run", None)
    return {"id": node["id"], "class_type": "S1LoraAggregate", "inputs": inputs}


def _convert_collect(node, by_id, warnings: list[str]) -> dict[str, Any]:
    inputs = dict(node["inputs"])
    for name in ("a", "b"):
        link = inputs.get(name)
        parent_id = _link_node_id(link)
        parent = by_id.get(parent_id) if parent_id else None
        if parent and parent["class_type"] == "S1Theme":
            warnings.append(
                f"node {node['id']!r}: input {name} linked to {link!r}, which was theme_result. "
                "Retarget it to the option slot that should merge."
            )
            inputs[name] = None
    return {"id": node["id"], "class_type": "S1ThemeCollect", "inputs": inputs}


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
    "migrate_router_graph",
    "migrate_theme_document",
    "migrate_theme_library",
    "plan_sequence",
    "retag_lora_library",
]
