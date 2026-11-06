"""Editor helpers for LoRA ids and a shared strength.

`js/s1_model.js` mirrors `next_lora_id` and `ensure_lora_ids` (`assignLoraIds`
and `nextLoraId`). `parse_lora_library` does not call this module. Stored JSON
still requires `lora_id`, `strength_model`, and `strength_clip`.

Id rule: the smallest unused positive integer, formatted `lora_N` (`lora_1`,
then `lora_2`, filling gaps). A non-empty `lora_id` is kept, including manual
ids such as `style_anime_v3`. Blank means missing, `None`, `""`, or whitespace.

Shared strength: one number is written to both `strength_model` and
`strength_clip`. Stored JSON has no `strength` key.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

__all__ = [
    "apply_shared_strength",
    "ensure_lora_ids",
    "next_lora_id",
    "shared_strength_fields",
]


def next_lora_id(existing_ids: Iterable[object]) -> str:
    """Return the smallest `lora_N` (N >= 1) that is not already in `existing_ids`."""

    used: set[str] = set()
    for item in existing_ids:
        if isinstance(item, str) and item != "":
            used.add(item)
    number = 1
    while f"lora_{number}" in used:
        number += 1
    return f"lora_{number}"


def _id_kept(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def ensure_lora_ids(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy `entries` and fill blank `lora_id` values.

    Non-empty ids are copied unchanged. Assignment looks at every kept id
    first, so a blank earlier in the list cannot take an id that a later
    entry already uses. The input list and its dicts are not mutated.
    """

    if not isinstance(entries, list):
        raise TypeError("entries must be a list")
    filled: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise TypeError("each entry must be a dict")
        filled.append(dict(entry))
    seen: list[str] = []
    for item in filled:
        raw = item.get("lora_id")
        if _id_kept(raw):
            seen.append(raw)
    for item in filled:
        if _id_kept(item.get("lora_id")):
            continue
        new_id = next_lora_id(seen)
        item["lora_id"] = new_id
        seen.append(new_id)
    return filled


def _finite_strength(strength: Any) -> int | float:
    if isinstance(strength, bool) or not isinstance(strength, (int, float)):
        raise TypeError("strength must be a finite number")
    if not math.isfinite(strength):
        raise ValueError("strength must be a finite number")
    return strength


def shared_strength_fields(strength: Any) -> dict[str, int | float]:
    """Return `strength_model` and `strength_clip` set to the same number."""

    value = _finite_strength(strength)
    return {"strength_model": value, "strength_clip": value}


def apply_shared_strength(entry: dict[str, Any], strength: Any) -> dict[str, Any]:
    """Copy `entry` and set both strength fields to `strength`.

    A `strength` key on the input is dropped. Callers keep any other fields,
    including a manual `lora_id`.
    """

    if not isinstance(entry, dict):
        raise TypeError("entry must be a dict")
    value = _finite_strength(strength)
    out = dict(entry)
    out.pop("strength", None)
    out["strength_model"] = value
    out["strength_clip"] = value
    return out
