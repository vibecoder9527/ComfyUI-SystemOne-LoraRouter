"""Match accumulated theme tags to the LoRA library and apply each LoRA once.

``enabled_default`` true (always-on): the entry is applied regardless of tags.
``enabled_default`` false (tag-gated): the entry is applied only when any of
its library tags shares a name with a selected option tag. Comparison is
case-insensitive and ignores an optional ``:weight`` suffix on option tags
(``age:-2`` matches library tag ``age``).

When a matching option tag carries a weight, that weight overrides both
``strength_model`` and ``strength_clip``. Unweighted hits keep the library
strengths. Weight ``0`` skips loading (listed under ``skipped`` with reason
``weight_0``), including Default On entries. Several weighted hits on the
same LoRA (including across themes) use the weight with the greatest
absolute value; a tie keeps the first hit in Theme Result decision order,
then option_tags order, then tag order. Weights outside -5..5 are clamped
with a warning. A negative weight on a non-slider entry is still applied
and records a warning. Entries are applied in ``lora_id`` order through
``apply_loras``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .apply_loras import apply_loras
from .schema.blocker import is_execution_blocker
from .schema.tags import clamp_strength, parse_tag
from .schema.types import (
    DecisionPayload,
    LoraLibrary,
    SchemaError,
    ThemeDecision,
    ThemeResult,
    build_theme_result,
    public_decision,
)
from .theme_engine import dump_report

_ON_ERROR = {"passthrough", "raise"}


@dataclass
class AggregateOutcome:
    model: Any
    clip: Any
    report: dict[str, Any] = field(default_factory=dict)


def _result_of(decision: DecisionPayload) -> ThemeResult:
    if not isinstance(decision, DecisionPayload):
        raise SchemaError(
            "decision must be an S1_DECISION from a Theme option slot or Theme Collect"
        )
    result = decision.result
    if not isinstance(result, ThemeResult):
        raise SchemaError("S1_DECISION is missing an accumulated result")
    return result


def match_loras(lora_lib: LoraLibrary, decision: DecisionPayload) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return ``(matched, skipped)`` without loading weight files.

    ``matched`` items use the ``apply_loras`` shape plus ``matched_tags``,
    ``weight_source``, ``slider``, and ``warnings``. Always-on entries
    (``enabled_default`` true) are matched even with no tag overlap;
    ``matched_tags`` / ``sources`` are then empty and strengths come from
    the library, unless a weighted tag also hits. Tag-gated entries match
    only on a name overlap. ``skipped`` lists entries whose resolved
    weight is 0. Tag-gated entries with no overlap are omitted.
    """

    if not isinstance(lora_lib, LoraLibrary):
        raise SchemaError("lora_lib must be an S1_LORA_LIB from S1LoraLibrary")
    result = _result_of(decision)
    matched: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for lora_id in sorted(lora_lib.loras):
        entry = lora_lib.loras[lora_id]
        library_keys = {parse_tag(tag).name_key: tag for tag in entry.tags if parse_tag(tag).name}
        hits = _option_hits(result, library_keys)
        overlap = _matched_library_tags(entry.tags, hits)
        sources = [[hit["theme_id"], hit["option_id"], hit["tag"]] for hit in hits]
        always_on = entry.enabled_default
        if not always_on and not hits:
            continue
        item, skip = _resolve_strength(entry, lora_id, hits, overlap, sources)
        if skip:
            skipped.append(item)
        else:
            matched.append(item)
    return matched, skipped


def _option_hits(result: ThemeResult, library_keys: dict[str, str]) -> list[dict[str, Any]]:
    """Option-tag hits in theme / option / tag order."""

    hits: list[dict[str, Any]] = []
    for decision in result.decisions:
        if decision.status != "ok":
            continue
        for option_id, option_tags in decision.option_tags:
            for raw in option_tags:
                parsed = parse_tag(raw)
                if not parsed.name or parsed.name_key not in library_keys:
                    continue
                hits.append(
                    {
                        "theme_id": decision.theme_id,
                        "option_id": option_id,
                        "tag": raw,
                        "parsed": parsed,
                    }
                )
    return hits


def _matched_library_tags(library_tags: list[str], hits: list[dict[str, Any]]) -> list[str]:
    """Library tag spellings that a hit reached, in library order."""

    hit_keys = {hit["parsed"].name_key for hit in hits}
    overlap: list[str] = []
    seen: set[str] = set()
    for tag in library_tags:
        parsed = parse_tag(tag)
        if parsed.name_key not in hit_keys or tag in seen:
            continue
        seen.add(tag)
        overlap.append(tag)
    return overlap


def _resolve_strength(entry, lora_id: str, hits: list[dict[str, Any]], overlap: list[str], sources: list[list[str]]):
    """Pick library strengths or an overriding option weight."""

    warnings: list[str] = []
    weighted = [hit for hit in hits if hit["parsed"].has_weight]
    if weighted:
        chosen = weighted[0]
        for hit in weighted[1:]:
            if abs(hit["parsed"].weight) > abs(chosen["parsed"].weight):
                chosen = hit
        raw_weight = float(chosen["parsed"].weight)
        strength, clamped = clamp_strength(raw_weight)
        if clamped:
            warnings.append(
                f"LoRA {lora_id}: tag weight {raw_weight} was clamped to {strength} (range -5..5)."
            )
        if not entry.slider and strength < 0:
            warnings.append(
                f"LoRA {lora_id}: weighted tag {chosen['tag']!r} applied a negative "
                f"strength ({strength}) to a non-slider entry."
            )
        weight_source = {
            "kind": "tag",
            "theme_id": chosen["theme_id"],
            "option_id": chosen["option_id"],
            "tag": chosen["tag"],
            "tag_name": chosen["parsed"].name,
            "weight": strength,
            "requested_weight": raw_weight,
        }
        strength_model = strength
        strength_clip = strength
    else:
        strength_model = entry.strength_model
        strength_clip = entry.strength_clip
        weight_source = {"kind": "library"}

    item = {
        "lora_id": lora_id,
        "name": entry.name,
        "strength_model": strength_model,
        "strength_clip": strength_clip,
        "matched_tags": overlap,
        "sources": sources,
        "slider": bool(entry.slider),
        "weight_source": weight_source,
        "warnings": warnings,
    }
    if weighted and float(item["strength_model"]) == 0.0:
        item["reason"] = "weight_0"
        item["skipped"] = True
        return item, True
    return item, False



def aggregate_loras(
    *,
    model: Any,
    clip: Any,
    lora_lib: LoraLibrary,
    decision: DecisionPayload,
    on_error: str = "passthrough",
) -> AggregateOutcome:
    """Apply each matched LoRA once. ``on_error`` is forwarded to ``apply_loras``."""

    if on_error not in _ON_ERROR:
        raise SchemaError(f"on_error must be one of: {', '.join(sorted(_ON_ERROR))}")
    theme_result = _result_of(decision)
    matched, skipped = match_loras(lora_lib, decision)
    apply_items = [
        {
            "lora_id": item["lora_id"],
            "name": item["name"],
            "strength_model": item["strength_model"],
            "strength_clip": item["strength_clip"],
            "sources": item["sources"],
            "slider": item.get("slider", False),
            "weight_source": item.get("weight_source", {"kind": "library"}),
            "warnings": list(item.get("warnings") or []),
        }
        for item in matched
    ]
    outcome = apply_loras(model, clip, apply_items, on_error=on_error)
    notes = list(outcome.notes)
    warnings: list[str] = []
    for item in matched:
        warnings.extend(item.get("warnings") or [])
    for item in skipped:
        warnings.extend(item.get("warnings") or [])
    if skipped:
        names = ", ".join(item["lora_id"] for item in skipped)
        reasons = {item.get("reason") for item in skipped}
        if reasons <= {"weight_0"}:
            notes.append(f"Skipped LoRA(s) at weight 0: {names}.")
        else:
            notes.append(f"Skipped LoRA(s): {names}.")
    if theme_result.errors:
        notes.append(
            "The decision already recorded theme errors. Matching still used the tags it kept."
        )
    report = {
        "tags": list(theme_result.tags),
        "themes": [public_decision(decision) for decision in theme_result.decisions],
        "matched": matched,
        "skipped": skipped,
        "applied": outcome.applied,
        "errors": list(theme_result.errors) + list(outcome.errors),
        "notes": notes,
        "warnings": warnings,
    }
    return AggregateOutcome(model=outcome.model, clip=outcome.clip, report=report)


def _same_decision(left: ThemeDecision, right: ThemeDecision) -> bool:
    """True when two snapshots are the same decision, including ``raw``.

    ``raw`` does not change tag matching, but a different stored answer is not
    the same ancestor. Collect drops only a full match.
    """

    left_options = [(option_id, list(tags)) for option_id, tags in left.option_tags]
    right_options = [(option_id, list(tags)) for option_id, tags in right.option_tags]
    return (
        left.theme_id == right.theme_id
        and left.status == right.status
        and left.enabled == right.enabled
        and list(left.selected) == list(right.selected)
        and list(left.tags) == list(right.tags)
        and left.select_mode == right.select_mode
        and left_options == right_options
        and left.error == right.error
        and left.reason == right.reason
        and left.raw == right.raw
    )


def _merge_errors(left: ThemeResult, right: ThemeResult) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for item in list(left.errors) + list(right.errors):
        if item in seen:
            continue
        seen.add(item)
        merged.append(item)
    return merged


def collect_theme_results(left: ThemeResult, right: ThemeResult) -> ThemeResult:
    """Keep input ``a`` first, then new ids from ``b``.

    An identical later decision for a ``theme_id`` already kept is dropped, so
    a diamond that shares an ancestor contributes that decision and its tags
    once. A different decision for the same id raises ``SchemaError``.
    """

    if not isinstance(left, ThemeResult) or not isinstance(right, ThemeResult):
        raise SchemaError("accumulated results must be ThemeResult values")
    merged: list[ThemeDecision] = []
    kept: dict[str, ThemeDecision] = {}
    for decision in list(left.decisions) + list(right.decisions):
        if not isinstance(decision, ThemeDecision):
            raise SchemaError("theme result decisions must be ThemeDecision values")
        previous = kept.get(decision.theme_id)
        if previous is None:
            kept[decision.theme_id] = decision
            merged.append(decision)
            continue
        if _same_decision(previous, decision):
            continue
        raise SchemaError(
            f"conflicting theme_id {decision.theme_id!r} in the theme result: "
            "the collected decisions do not match"
        )
    return build_theme_result(merged, _merge_errors(left, right))


def _collectable(value: Any) -> DecisionPayload | None:
    """Return a real payload, or None for a missing / blocked optional input.

    An ``ExecutionBlocker`` is ignored so a selected sibling can still merge.
    Anything else that is not an ``S1_DECISION`` raises.
    """

    if value is None:
        return None
    if is_execution_blocker(value):
        return None
    if isinstance(value, DecisionPayload):
        return value
    raise SchemaError("Theme Collect inputs must be S1_DECISION values")


def collect_decisions(*payloads: Any) -> DecisionPayload:
    """Merge option-slot payloads in argument order.

    Missing inputs and ``ExecutionBlocker`` values are ignored. One real
    ``S1_DECISION`` is returned unchanged. Two or more real payloads merge:
    a conflicting decision for the same ``theme_id`` raises ``SchemaError``.
    Zero usable inputs raises ``SchemaError``. A merged output has an empty
    slot id and can feed another Theme, another Collect, or LoRA Aggregate.
    """

    usable = [item for item in (_collectable(value) for value in payloads) if item is not None]
    if not usable:
        raise SchemaError(
            "Theme Collect needs an S1_DECISION on at least one input; "
            "every input was missing or blocked"
        )
    if len(usable) == 1:
        return usable[0]
    merged = usable[0].result
    for item in usable[1:]:
        merged = collect_theme_results(merged, item.result)
    return DecisionPayload(
        result=merged,
        slot_option_id="",
        theme_id="",
        emitted_reason="collected",
    )


__all__ = [
    "AggregateOutcome",
    "aggregate_loras",
    "collect_decisions",
    "collect_theme_results",
    "dump_report",
    "match_loras",
]
