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
from .schema.types import (
    LoraLibrary,
    SchemaError,
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


def match_loras(lora_lib: LoraLibrary, result: ThemeResult) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return ``(matched, skipped)`` without loading weight files.

    ``matched`` items use the ``apply_loras`` shape plus ``matched_tags``.
    ``skipped`` lists library entries that shared a tag but ``enabled_default``
    is false. Entries with no tag overlap are omitted.
    """

    if not isinstance(lora_lib, LoraLibrary):
        raise SchemaError("lora_lib must be an S1_LORA_LIB from S1LoraLibrary")
    if not isinstance(result, ThemeResult):
        raise SchemaError("theme_result must be an S1_THEME_RESULT")
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
    theme_result: ThemeResult,
    on_error: str = "passthrough",
) -> AggregateOutcome:
    """Apply each matched LoRA once. ``on_error`` is forwarded to ``apply_loras``."""

    if on_error not in _ON_ERROR:
        raise SchemaError(f"on_error must be one of: {', '.join(sorted(_ON_ERROR))}")
    matched, skipped = match_loras(lora_lib, theme_result)
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
        notes.append("Theme result already recorded errors. Matching still used the tags it kept.")
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


def collect_theme_results(left: ThemeResult, right: ThemeResult) -> ThemeResult:
    """Append `right` after `left`. A repeated theme id raises ``SchemaError``."""

    if not isinstance(left, ThemeResult) or not isinstance(right, ThemeResult):
        raise SchemaError("Theme Collect inputs must be S1_THEME_RESULT values")
    return build_theme_result(
        list(left.decisions) + list(right.decisions),
        list(left.errors) + list(right.errors),
    )


__all__ = [
    "AggregateOutcome",
    "aggregate_loras",
    "collect_theme_results",
    "dump_report",
    "match_loras",
]
