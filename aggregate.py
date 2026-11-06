"""Match accumulated theme tags to the LoRA library and apply each LoRA once.

A library entry matches when ``enabled_default`` is true and any of its tags
is in the result's tag list. Comparison is exact. The library
``strength_model`` and ``strength_clip`` are the only strengths. Entries are
applied in ``lora_id`` order through ``apply_loras``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .apply_loras import apply_loras
from .schema.blocker import is_execution_blocker
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

    ``matched`` items use the ``apply_loras`` shape plus ``matched_tags``.
    ``skipped`` lists library entries that shared a tag but ``enabled_default``
    is false. Entries with no tag overlap are omitted.
    """

    if not isinstance(lora_lib, LoraLibrary):
        raise SchemaError("lora_lib must be an S1_LORA_LIB from S1LoraLibrary")
    result = _result_of(decision)
    tag_sources: dict[str, list[list[str]]] = {}
    for decision in result.decisions:
        if decision.status != "ok":
            continue
        for option_id, option_tags in decision.option_tags:
            for tag in option_tags:
                tag_sources.setdefault(tag, []).append([decision.theme_id, option_id, tag])
    selected = set(result.tags)
    matched: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for lora_id in sorted(lora_lib.loras):
        entry = lora_lib.loras[lora_id]
        overlap: list[str] = []
        seen_tags: set[str] = set()
        for tag in entry.tags:
            if tag in selected and tag not in seen_tags:
                seen_tags.add(tag)
                overlap.append(tag)
        if not overlap:
            continue
        if not entry.enabled_default:
            skipped.append({"lora_id": lora_id, "reason": "enabled_default is false"})
            continue
        sources: list[list[str]] = []
        for tag in overlap:
            sources.extend(tag_sources.get(tag, []))
        matched.append(
            {
                "lora_id": lora_id,
                "name": entry.name,
                "strength_model": entry.strength_model,
                "strength_clip": entry.strength_clip,
                "matched_tags": overlap,
                "sources": sources,
            }
        )
    return matched, skipped


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
        }
        for item in matched
    ]
    outcome = apply_loras(model, clip, apply_items, on_error=on_error)
    notes = list(outcome.notes)
    if skipped:
        names = ", ".join(item["lora_id"] for item in skipped)
        notes.append(f"Skipped LoRA(s) with enabled_default false: {names}.")
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


def collect_decisions(left: Any = None, right: Any = None) -> DecisionPayload:
    """Merge two option-slot payloads. Identical theme ids collapse once.

    Missing inputs and ``ExecutionBlocker`` values are ignored. One real
    ``S1_DECISION`` is returned unchanged. Two real payloads merge: a
    conflicting decision for the same ``theme_id`` raises ``SchemaError``.
    Zero usable inputs raises ``SchemaError``. A merged output has an empty
    slot id and can feed another Theme, another Collect, or LoRA Aggregate.
    """

    first = _collectable(left)
    second = _collectable(right)
    if first is None and second is None:
        raise SchemaError(
            "Theme Collect needs an S1_DECISION on a or b; both were missing or blocked"
        )
    if first is None:
        return second
    if second is None:
        return first
    merged = collect_theme_results(first.result, second.result)
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
