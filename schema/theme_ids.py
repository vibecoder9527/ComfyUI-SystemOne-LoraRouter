"""Editor helpers for theme ids and option ids.

`js/s1_model.js` mirrors these (`assignThemeIds`, `nextThemeId`, `nextOptionId`).
`parse_theme_library` does not call this module. Stored JSON still requires
`theme_id` and `option_id`.

Theme ids are unique in the library. Option ids are unique within one theme.
The smallest unused positive integer wins: `theme_1`, `theme_2`, `option_1`,
`option_2`, filling gaps. A non-empty id is kept, including manual ids such as
`art_style` or `anime`. Blank means missing, `None`, `""`, or whitespace.

Filling an id does not rewrite sequence steps. Those still cite `theme_id`
by the string the user stored.
"""

from __future__ import annotations

from typing import Any, Iterable

__all__ = [
    "ensure_option_ids",
    "ensure_theme_ids",
    "next_option_id",
    "next_theme_id",
]


def _next_id(prefix: str, existing_ids: Iterable[object]) -> str:
    used: set[str] = set()
    for item in existing_ids:
        if isinstance(item, str) and item != "":
            used.add(item)
    number = 1
    while f"{prefix}{number}" in used:
        number += 1
    return f"{prefix}{number}"


def next_theme_id(existing_ids: Iterable[object]) -> str:
    """Return the smallest `theme_N` (N >= 1) that is not already in `existing_ids`."""

    return _next_id("theme_", existing_ids)


def next_option_id(existing_ids: Iterable[object]) -> str:
    """Return the smallest `option_N` (N >= 1) that is not already in `existing_ids`."""

    return _next_id("option_", existing_ids)


def _id_kept(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _fill_ids(entries: list[dict[str, Any]], key: str, nxt) -> None:
    seen: list[str] = []
    for item in entries:
        raw = item.get(key)
        if _id_kept(raw):
            seen.append(raw)
    for item in entries:
        if _id_kept(item.get(key)):
            continue
        new_id = nxt(seen)
        item[key] = new_id
        seen.append(new_id)


def ensure_option_ids(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy `options` and fill blank `option_id` values inside this theme.

    Non-empty ids are copied unchanged. Assignment looks at every kept id in
    this list first, so a blank earlier in the list cannot take an id that a
    later option already uses. Other themes are not consulted. The input list
    and its dicts are not mutated.
    """

    if not isinstance(options, list):
        raise TypeError("options must be a list")
    filled: list[dict[str, Any]] = []
    for option in options:
        if not isinstance(option, dict):
            raise TypeError("each option must be a dict")
        filled.append(dict(option))
    _fill_ids(filled, "option_id", next_option_id)
    return filled


def ensure_theme_ids(themes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy `themes`, fill blank `theme_id` values, and fill option ids per theme.

    Option ids are scoped to that theme's `options` list. A theme with no
    `options` key is left without one. The input list and its dicts are not
    mutated.
    """

    if not isinstance(themes, list):
        raise TypeError("themes must be a list")
    filled: list[dict[str, Any]] = []
    for theme in themes:
        if not isinstance(theme, dict):
            raise TypeError("each theme must be a dict")
        copy = dict(theme)
        if "options" in copy:
            copy["options"] = ensure_option_ids(copy["options"])
        filled.append(copy)
    _fill_ids(filled, "theme_id", next_theme_id)
    return filled
