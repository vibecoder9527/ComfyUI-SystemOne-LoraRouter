"""Default 以上皆非 option for Theme / Theme Root.

A theme always has a none-of-the-above choice with its own output slot.
Existing none_option_id values, and options that already look like a none
choice (label/id/description), are reused so old workflows keep their
slot indexes and wires.
"""

from __future__ import annotations

from typing import Any

DEFAULT_NONE_LABEL = "以上皆非"
DEFAULT_NONE_DESCRIPTION = "以上皆非"
PREFERRED_NONE_OPTION_ID = "none"
NONE_LIKE_IDS = frozenset({"none", "__none__", "以上皆非"})
NONE_LIKE_LABELS = frozenset(
    {
        "以上皆非",
        "none",
        "none of the above",
        "not on the list",
    }
)


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def is_none_like_option(option: dict[str, Any] | None) -> bool:
    if not isinstance(option, dict):
        return False
    option_id = _norm(option.get("option_id"))
    if option_id in {_norm(item) for item in NONE_LIKE_IDS}:
        return True
    label = _norm(option.get("label"))
    if label in NONE_LIKE_LABELS:
        return True
    description = _norm(option.get("description"))
    if description in NONE_LIKE_LABELS:
        return True
    return False


def _next_none_id(existing: set[str]) -> str:
    if PREFERRED_NONE_OPTION_ID not in existing:
        return PREFERRED_NONE_OPTION_ID
    index = 2
    while True:
        candidate = f"{PREFERRED_NONE_OPTION_ID}_{index}"
        if candidate not in existing:
            return candidate
        index += 1


def ensure_default_none_option(
    document: dict[str, Any],
    *,
    max_options: int | None = None,
) -> dict[str, Any]:
    """Return a copy with a none option and none_option_id set.

    Reuses an existing none_option_id or a none-like option. Otherwise
    appends a new option so earlier slot indexes stay put.
    """

    from .types import MAX_OPTION_OUTPUTS, SchemaError

    cap = MAX_OPTION_OUTPUTS if max_options is None else max_options
    out = dict(document)
    options = [dict(item) if isinstance(item, dict) else item for item in (out.get("options") or [])]
    known = {
        str(item.get("option_id"))
        for item in options
        if isinstance(item, dict) and item.get("option_id")
    }
    current = out.get("none_option_id") or ""
    current = str(current).strip()
    if current and current in known:
        out["options"] = options
        out["none_option_id"] = current
        return out
    for item in options:
        if is_none_like_option(item):
            option_id = str(item.get("option_id") or "").strip()
            if not option_id:
                option_id = _next_none_id(known)
                item["option_id"] = option_id
                known.add(option_id)
            out["options"] = options
            out["none_option_id"] = option_id
            return out
    if len(options) >= cap:
        raise SchemaError(
            f"cannot add {DEFAULT_NONE_LABEL!r}; option outputs are capped at {cap}"
        )
    option_id = _next_none_id(known)
    options.append(
        {
            "option_id": option_id,
            "label": DEFAULT_NONE_LABEL,
            "description": DEFAULT_NONE_DESCRIPTION,
            "tags": [],
        }
    )
    out["options"] = options
    out["none_option_id"] = option_id
    return out
