"""Parse option tags of the form ``name`` or ``name:weight``.

Library tags stay plain names (``age``). Theme option tags may carry an
optional weight: ``age:-2``, ``age:0``, ``age:+1.5`` (the plus is optional).
The plus-minus sign is not a weight syntax. Matching compares names only,
case-insensitively, and ignores the ``:weight`` suffix.

Canonical storage for a weighted tag is ``name:weight`` with no plus on a
positive number (``age:-2``, ``age:1.5``). Unweighted tags stay the bare
name. Old documents that stored only plain strings remain valid.
"""

from __future__ import annotations

import re
from typing import NamedTuple

SLIDER_STRENGTH_MIN = -5.0
SLIDER_STRENGTH_MAX = 5.0

# Decimal weight after the last colon. Optional leading + or -. Not scientific.
_WEIGHT_SUFFIX = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")


class ParsedTag(NamedTuple):
    name: str
    weight: float | None
    raw: str

    @property
    def has_weight(self) -> bool:
        return self.weight is not None

    @property
    def name_key(self) -> str:
        return self.name.casefold()

    @property
    def canonical(self) -> str:
        return format_tag(self.name, self.weight)


def parse_tag(value: str) -> ParsedTag:
    """Split ``name`` or ``name:weight``. Non-numeric suffixes stay in the name."""

    raw = str(value).strip()
    name, weight = _split_weight(raw)
    return ParsedTag(name=name, weight=weight, raw=raw)


def format_tag(name: str, weight: float | None = None) -> str:
    text = str(name).strip()
    if weight is None:
        return text
    return f"{text}:{format_weight(weight)}"


def format_weight(value: float) -> str:
    number = float(value)
    if number == int(number) and abs(number) < 1e15:
        return str(int(number))
    text = f"{number:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def format_chip_label(tag: ParsedTag | str) -> str:
    """Chip text: ``age`` or ``age −2`` (Unicode minus)."""

    parsed = tag if isinstance(tag, ParsedTag) else parse_tag(tag)
    if parsed.weight is None:
        return parsed.name
    shown = format_weight(parsed.weight)
    if shown.startswith("-"):
        shown = "\u2212" + shown[1:]
    return f"{parsed.name} {shown}"


def clamp_strength(value: float) -> tuple[float, bool]:
    """Clamp to ``-5..5``. Return ``(clamped, was_clamped)``."""

    number = float(value)
    if number < SLIDER_STRENGTH_MIN:
        return SLIDER_STRENGTH_MIN, True
    if number > SLIDER_STRENGTH_MAX:
        return SLIDER_STRENGTH_MAX, True
    return number, False


def library_tag_name(value: str) -> str:
    """Library tags are identifiers only; any ``:weight`` suffix is dropped."""

    return parse_tag(value).name


def normalize_library_tags(tags: list[str]) -> list[str]:
    """Plain names. Weights are stripped. Distinct stored spellings are kept."""

    out: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        name = library_tag_name(raw)
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _split_weight(raw: str) -> tuple[str, float | None]:
    if ":" not in raw:
        return raw, None
    head, _, tail = raw.rpartition(":")
    name = head.strip()
    suffix = tail.strip()
    if not name or not _WEIGHT_SUFFIX.fullmatch(suffix):
        return raw, None
    try:
        weight = float(suffix)
    except ValueError:
        return raw, None
    if weight != weight or weight in (float("inf"), float("-inf")):
        return raw, None
    return name, weight
