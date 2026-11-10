"""Default None option for Theme / Theme Root.

A theme always has a none-of-the-above choice with its own output slot.
Existing none_option_id values, and options that already look like a none
choice (label/id/description), are reused so old workflows keep their
slot indexes and wires.
"""

from __future__ import annotations

from typing import Any

DEFAULT_NONE_LABEL = "None"
DEFAULT_NONE_DESCRIPTION = "None"
PREFERRED_NONE_OPTION_ID = "none"
# Former auto-generated default. Kept only to recognize and relabel saved None rows.
LEGACY_DEFAULT_NONE_TEXT = "以上皆非"
NONE_LIKE_IDS = frozenset({"none", "__none__", LEGACY_DEFAULT_NONE_TEXT})
NONE_LIKE_LABELS = frozenset(
    {
        LEGACY_DEFAULT_NONE_TEXT,
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


def is_legacy_default_none_text(value: Any) -> bool:
    """True only when a field is exactly the former auto-generated default."""

    return str(value or "").strip() == LEGACY_DEFAULT_NONE_TEXT


def relabel_legacy_default_none_option(option: dict[str, Any] | None) -> bool:
    """Rewrite auto-generated default fields on the designated None option.

    Only a field whose trimmed text is exactly LEGACY_DEFAULT_NONE_TEXT is
    changed to DEFAULT_NONE_LABEL / DEFAULT_NONE_DESCRIPTION. User-typed
    text, tags, option_id, and every other option are left alone.
    """

    if not isinstance(option, dict):
        return False
    changed = False
    if is_legacy_default_none_text(option.get("label")):
        option["label"] = DEFAULT_NONE_LABEL
        changed = True
    if is_legacy_default_none_text(option.get("description")):
        option["description"] = DEFAULT_NONE_DESCRIPTION
        changed = True
    return changed


def _apply_legacy_none_relabel(options: list[Any], none_option_id: str) -> bool:
    none_id = str(none_option_id or "").strip()
    if not none_id:
        return False
    for item in options:
        if isinstance(item, dict) and str(item.get("option_id") or "") == none_id:
            return relabel_legacy_default_none_option(item)
    return False


def ensure_default_none_option(
    document: dict[str, Any],
    *,
    max_options: int | None = None,
) -> dict[str, Any]:
    """Return a copy with a none option and none_option_id set.

    Reuses an existing none_option_id or a none-like option. Otherwise
    appends a new option so earlier slot indexes stay put. A designated
    None option whose label/description is still the former auto-generated
    default is relabeled to "None".
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
        _apply_legacy_none_relabel(options, current)
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
            _apply_legacy_none_relabel(options, option_id)
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
