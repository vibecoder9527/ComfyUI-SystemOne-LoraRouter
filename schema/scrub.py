"""Scrub SystemOne Settings secrets out of PNG metadata.

Only ``S1Settings.api_key`` and ``S1Settings.endpoint`` are touched. Every
other prompt input, widget value, and extra_pnginfo key is left as it was.

Three layers, all on deep copies (the live prompt / extra_pnginfo objects
that execution keeps using are never mutated):

1. ``prompt`` (API format): each ``S1Settings`` node gets ``""`` for those
   inputs when they are literal strings. A link ``[node_id, slot]`` is left
   alone; layer 3 scrubs the value at its source.
2. ``extra_pnginfo["workflow"]``: each ``S1Settings`` node's
   ``widgets_values`` is positional, in ``INPUT_TYPES`` widget order (plus
   one extra slot after any widget with ``control_after_generate``; the
   frontend keeps a slot for a widget converted to an input). A dict is
   handled by name. ``definitions.subgraphs[*]`` are walked recursively.
3. Safety net: the literal values (from the prompt, following links to a
   Primitive / String source node, and from workflow widgets and linked
   PrimitiveNodes) are replaced with ``""`` in every string leaf and dict
   key of the prompt and of every extra_pnginfo value. Values shorter than
   ``MIN_SAFETY_NET_LENGTH`` are only cleared by field (layers 1-2), so a
   short value never rewrites unrelated text. Empty strings never match.

``""`` is the replacement: it is both inputs' default-equivalent. A blank
``api_key`` falls back to ``SYSTEM_ONE_API_KEY``; a blank ``endpoint`` is the
SystemOne default in ``build_settings``. A reloaded workflow therefore
validates and runs (with the env key). ``"[redacted]"`` would fail the
endpoint's http(s) check and would be sent as a bearer token.
"""

from __future__ import annotations

import copy
import json
import struct
import zlib
from typing import Any, Iterable

SETTINGS_CLASS = "S1Settings"
SCRUB_FIELDS = ("api_key", "endpoint")
REDACTED = ""
MIN_SAFETY_NET_LENGTH = 6
_LINK_DEPTH = 8
# Source-node inputs that carry the string of a Primitive / String node.
_SOURCE_VALUE_KEYS = ("value", "string", "text", "String", "STRING", "Text")
_WIDGET_TYPES = {"STRING", "INT", "FLOAT", "BOOLEAN", "COMBO"}

__all__ = [
    "MIN_SAFETY_NET_LENGTH",
    "REDACTED",
    "SCRUB_FIELDS",
    "SETTINGS_CLASS",
    "ScrubVerificationError",
    "collect_secret_values",
    "png_text_chunks",
    "scrub_metadata",
    "scrub_prompt",
    "scrub_workflow",
    "settings_widget_indices",
    "verify_png_scrubbed",
    "widget_value_layout",
]


class ScrubVerificationError(RuntimeError):
    """A scrubbed value is still present in a written PNG."""


# ---------------------------------------------------------------- layout


def _is_widget(spec: Any) -> bool:
    if not isinstance(spec, (list, tuple)) or not spec:
        return False
    kind = spec[0]
    options = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
    if options.get("forceInput"):
        return False
    if isinstance(kind, (list, tuple)):
        return True
    return isinstance(kind, str) and kind in _WIDGET_TYPES


def _has_control_slot(name: str, spec: Any) -> bool:
    options = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
    if options.get("control_after_generate"):
        return True
    return spec[0] == "INT" and name in ("seed", "noise_seed")


def widget_value_layout(input_types: dict[str, Any]) -> list[str]:
    """Names per ``widgets_values`` slot. ``""`` marks a control slot."""

    layout: list[str] = []
    for section in ("required", "optional"):
        for name, spec in (input_types.get(section) or {}).items():
            if not _is_widget(spec):
                continue
            layout.append(name)
            if _has_control_slot(name, spec):
                layout.append("")
    return layout


def settings_widget_indices() -> dict[str, int]:
    """``{field: widgets_values index}`` for the scrubbed S1Settings fields."""

    from ..nodes.settings import S1Settings

    layout = widget_value_layout(S1Settings.INPUT_TYPES())
    return {name: layout.index(name) for name in SCRUB_FIELDS if name in layout}


# ---------------------------------------------------------------- helpers


def _is_link(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and isinstance(value[0], (str, int))
        and not isinstance(value[0], bool)
        and isinstance(value[1], int)
        and not isinstance(value[1], bool)
    )


def _node_type(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    return str(node.get("class_type") or node.get("type") or "")


def _graphs(workflow: Any) -> Iterable[dict[str, Any]]:
    """The root graph and every subgraph definition, nested ones included."""

    seen: set[int] = set()
    stack = [workflow]
    while stack:
        graph = stack.pop()
        if not isinstance(graph, dict) or id(graph) in seen:
            continue
        seen.add(id(graph))
        yield graph
        definitions = graph.get("definitions")
        if isinstance(definitions, dict):
            subgraphs = definitions.get("subgraphs")
            if isinstance(subgraphs, list):
                stack.extend(item for item in subgraphs if isinstance(item, dict))
        for node in graph.get("nodes") or []:
            # Some exports inline a subgraph on the node instead.
            if isinstance(node, dict) and isinstance(node.get("subgraph"), dict):
                stack.append(node["subgraph"])


def _link_record(link: Any) -> tuple[Any, Any] | None:
    """(origin_id, target_id-or-id) for array or object links; id first."""

    if isinstance(link, (list, tuple)) and len(link) >= 5:
        return link[0], link[1]
    if isinstance(link, dict):
        return link.get("id"), link.get("origin_id", link.get("originId"))
    return None


def _graph_link_origins(graph: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for link in graph.get("links") or []:
        record = _link_record(link)
        if record is not None and record[0] is not None:
            out[str(record[0])] = record[1]
    return out


def _string_widget_values(node: dict[str, Any]) -> list[str]:
    values = node.get("widgets_values")
    if isinstance(values, dict):
        values = list(values.values())
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, str)]


# ---------------------------------------------------------------- collect


def _resolve_prompt_value(prompt: dict[str, Any], value: Any, out: set[str], depth: int = 0) -> None:
    if depth > _LINK_DEPTH:
        return
    if isinstance(value, str):
        if value:
            out.add(value)
        return
    if not _is_link(value):
        return
    source = prompt.get(str(value[0]))
    if not isinstance(source, dict):
        return
    inputs = source.get("inputs")
    if not isinstance(inputs, dict):
        return
    for key in _SOURCE_VALUE_KEYS:
        if key in inputs:
            _resolve_prompt_value(prompt, inputs[key], out, depth + 1)
            return
    candidates = [item for item in inputs.values() if isinstance(item, str) or _is_link(item)]
    if len(candidates) == 1:
        _resolve_prompt_value(prompt, candidates[0], out, depth + 1)


def collect_secret_values(prompt: Any, workflow: Any = None) -> set[str]:
    """Literal api_key / endpoint strings to remove (non-empty)."""

    found: set[str] = set()
    if isinstance(prompt, dict):
        for node in prompt.values():
            if _node_type(node) != SETTINGS_CLASS:
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue
            for name in SCRUB_FIELDS:
                if name in inputs:
                    _resolve_prompt_value(prompt, inputs[name], found)
    indices = settings_widget_indices()
    for graph in _graphs(workflow):
        nodes = [node for node in graph.get("nodes") or [] if isinstance(node, dict)]
        by_id = {str(node.get("id")): node for node in nodes}
        origins = _graph_link_origins(graph)
        for node in nodes:
            if _node_type(node) != SETTINGS_CLASS:
                continue
            values = node.get("widgets_values")
            for name, index in indices.items():
                if isinstance(values, dict):
                    item = values.get(name)
                elif isinstance(values, list) and index < len(values):
                    item = values[index]
                else:
                    item = None
                if isinstance(item, str) and item:
                    found.add(item)
            for slot in node.get("inputs") or []:
                if not isinstance(slot, dict):
                    continue
                widget = slot.get("widget") if isinstance(slot.get("widget"), dict) else {}
                name = widget.get("name") or slot.get("name")
                if name not in SCRUB_FIELDS or slot.get("link") is None:
                    continue
                origin = by_id.get(str(origins.get(str(slot.get("link")))))
                if not origin:
                    continue
                strings = _string_widget_values(origin)
                if _node_type(origin) == "PrimitiveNode" and strings:
                    strings = strings[:1]
                if len(strings) == 1 and strings[0]:
                    found.add(strings[0])
    return found


# ---------------------------------------------------------------- scrub


def scrub_prompt(prompt: Any) -> Any:
    """Deep copy with S1Settings api_key / endpoint literals set to ``""``."""

    out = copy.deepcopy(prompt)
    if not isinstance(out, dict):
        return out
    for node in out.values():
        if _node_type(node) != SETTINGS_CLASS:
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for name in SCRUB_FIELDS:
            if isinstance(inputs.get(name), str):
                inputs[name] = REDACTED
    return out


def scrub_workflow(workflow: Any) -> Any:
    """Deep copy with S1Settings widget values cleared, subgraphs included."""

    out = copy.deepcopy(workflow)
    indices = settings_widget_indices()
    for graph in _graphs(out):
        for node in graph.get("nodes") or []:
            if _node_type(node) != SETTINGS_CLASS:
                continue
            values = node.get("widgets_values")
            if isinstance(values, dict):
                for name in SCRUB_FIELDS:
                    if isinstance(values.get(name), str):
                        values[name] = REDACTED
            elif isinstance(values, list):
                for index in indices.values():
                    if index < len(values) and isinstance(values[index], str):
                        values[index] = REDACTED
    return out


def _replace_all(data: Any, needles: list[str]) -> Any:
    if isinstance(data, str):
        for needle in needles:
            if needle in data:
                data = data.replace(needle, REDACTED)
        return data
    if isinstance(data, list):
        return [_replace_all(item, needles) for item in data]
    if isinstance(data, tuple):
        return tuple(_replace_all(item, needles) for item in data)
    if isinstance(data, dict):
        return {_replace_all(key, needles) if isinstance(key, str) else key: _replace_all(value, needles) for key, value in data.items()}
    return data


def _safety_needles(values: Iterable[str]) -> list[str]:
    return sorted(
        {value for value in values if isinstance(value, str) and len(value) >= MIN_SAFETY_NET_LENGTH},
        key=lambda value: (-len(value), value),
    )


def scrub_metadata(prompt: Any, extra_pnginfo: Any) -> tuple[Any, Any, set[str]]:
    """Return scrubbed copies of (prompt, extra_pnginfo) and the values removed."""

    workflow = extra_pnginfo.get("workflow") if isinstance(extra_pnginfo, dict) else None
    values = collect_secret_values(prompt, workflow)
    needles = _safety_needles(values)
    new_prompt = None
    if prompt is not None:
        new_prompt = _replace_all(scrub_prompt(prompt), needles)
    new_extra = None
    if extra_pnginfo is not None:
        new_extra = copy.deepcopy(extra_pnginfo)
        if isinstance(new_extra, dict):
            if "workflow" in new_extra:
                new_extra["workflow"] = scrub_workflow(new_extra["workflow"])
            new_extra = {key: _replace_all(value, needles) for key, value in new_extra.items()}
    return new_prompt, new_extra, values


# ---------------------------------------------------------------- verify


def png_text_chunks(path: str) -> dict[str, str]:
    """tEXt / zTXt / iTXt keyword -> text, read straight from the file."""

    out: dict[str, str] = {}
    with open(path, "rb") as handle:
        data = handle.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ScrubVerificationError(f"{path} is not a PNG file")
    pos = 8
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if kind == b"tEXt":
            key, _, text = body.partition(b"\x00")
            out[key.decode("latin-1")] = text.decode("latin-1")
        elif kind == b"zTXt":
            key, _, rest = body.partition(b"\x00")
            out[key.decode("latin-1")] = zlib.decompress(rest[1:]).decode("latin-1")
        elif kind == b"iTXt":
            key, _, rest = body.partition(b"\x00")
            compressed, rest = rest[0], rest[2:]
            _lang, _, rest = rest.partition(b"\x00")
            _translated, _, text = rest.partition(b"\x00")
            if compressed:
                text = zlib.decompress(text)
            out[key.decode("latin-1")] = text.decode("utf-8")
        elif kind == b"IEND":
            break
    return out


def _forms(value: str) -> set[str]:
    escaped = json.dumps(value)[1:-1]
    return {value, escaped, json.dumps(value, ensure_ascii=False)[1:-1]}


def _field_leaks(texts: dict[str, str]) -> list[str]:
    problems: list[str] = []
    raw = texts.get("prompt")
    if raw is not None:
        try:
            prompt = json.loads(raw)
        except ValueError:
            prompt = None
        if isinstance(prompt, dict):
            for node_id, node in prompt.items():
                if _node_type(node) != SETTINGS_CLASS or not isinstance(node.get("inputs"), dict):
                    continue
                for name in SCRUB_FIELDS:
                    value = node["inputs"].get(name)
                    if isinstance(value, str) and value != REDACTED:
                        problems.append(f"prompt node {node_id} {name}")
    raw = texts.get("workflow")
    if raw is not None:
        try:
            workflow = json.loads(raw)
        except ValueError:
            workflow = None
        indices = settings_widget_indices()
        for graph in _graphs(workflow):
            for node in graph.get("nodes") or []:
                if _node_type(node) != SETTINGS_CLASS:
                    continue
                values = node.get("widgets_values")
                for name, index in indices.items():
                    if isinstance(values, dict):
                        value = values.get(name)
                    elif isinstance(values, list) and index < len(values):
                        value = values[index]
                    else:
                        value = None
                    if isinstance(value, str) and value != REDACTED:
                        problems.append(f"workflow node {node.get('id')} {name}")
    return problems


def verify_png_scrubbed(path: str, values: Iterable[str]) -> None:
    """Raise ScrubVerificationError if a scrubbed value is still in the PNG.

    Never puts the value itself in the message.
    """

    texts = png_text_chunks(path)
    leaks = _field_leaks(texts)
    for value in _safety_needles(values):
        forms = _forms(value)
        for key, text in texts.items():
            if any(form and form in text for form in forms):
                leaks.append(f"text chunk {key!r} contains a scrubbed value ({len(value)} chars)")
    if leaks:
        raise ScrubVerificationError("S1 Save Image (Scrubbed): secret still present: " + "; ".join(sorted(set(leaks))))
