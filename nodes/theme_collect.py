"""Merge decision payloads so sibling option branches can share one Aggregate."""

from __future__ import annotations

from ..aggregate import collect_decisions

CATEGORY = "SystemOne/LoraRouter"

# a and b stay first so saved workflows keep their input names and links.
# Extra optional sockets (c, d, ...) let the frontend show a trailing empty
# slot when one more branch is connected.
MAX_COLLECT_INPUTS = 16
COLLECT_INPUT_NAMES = tuple(chr(ord("a") + index) for index in range(MAX_COLLECT_INPUTS))


class S1ThemeCollect:
    """Keep the first copy of each theme id. Conflicting decisions raise."""

    CATEGORY = CATEGORY
    FUNCTION = "merge"
    # ComfyUI 0.44 short-circuits on any ExecutionBlocker input. See execution_compat.
    IGNORE_OPTIONAL_EXECUTION_BLOCKERS = True
    RETURN_TYPES = ("S1_DECISION",)
    RETURN_NAMES = ("decision",)
    OUTPUT_TOOLTIPS = (
        "Merged S1_DECISION. Wire it into another Theme, another Theme Collect, "
        "or LoRA Aggregate. Tags are recomputed from the kept decisions.",
    )
    DESCRIPTION = (
        "Join optional S1_DECISION payloads. Use this when option branches "
        "should apply together. Inputs start as a and b so existing workflows "
        "keep their wires. Connecting a slot offers another empty one, up to "
        f"{MAX_COLLECT_INPUTS} inputs. An ExecutionBlocker or missing optional "
        "input is ignored so a selected sibling can stay linked and this node "
        "can run. ComfyUI 0.44 skips a node when any input is an ExecutionBlocker, "
        "including optional sockets; this pack sanitizes those optional blockers "
        "before that check. A mixed batch keeps live items; blocked items stay "
        "skipped for that slice only. Zero usable inputs raises SchemaError. "
        "Order is the first copy of each theme_id, in input order. "
        "The same decision for a theme_id already kept is dropped, so a shared "
        "ancestor is stored once. A different decision for that id raises SchemaError."
    )

    @classmethod
    def INPUT_TYPES(cls):
        optional = {}
        for index, name in enumerate(COLLECT_INPUT_NAMES):
            if index == 0:
                tip = (
                    "First decision. Optional. Its decisions stay first. "
                    "Unconnected or blocked is ignored."
                )
            elif index == 1:
                tip = (
                    "Second decision. Optional. New theme ids are appended after a. "
                    "Unconnected or blocked is ignored."
                )
            else:
                tip = (
                    f"Additional decision ({name}). Optional. "
                    "Unconnected or blocked is ignored."
                )
            optional[name] = (
                "S1_DECISION",
                {"forceInput": True, "tooltip": tip},
            )
        return {"required": {}, "optional": optional}

    def merge(self, *payloads, **named):
        allocated = {}
        extras = []
        for index, value in enumerate(payloads):
            if index < len(COLLECT_INPUT_NAMES):
                allocated[COLLECT_INPUT_NAMES[index]] = value
            else:
                extras.append(value)
        allocated.update(named)
        ordered = [allocated.get(name) for name in COLLECT_INPUT_NAMES if name in allocated]
        extras.extend(value for name, value in allocated.items() if name not in COLLECT_INPUT_NAMES)
        return (collect_decisions(*ordered, *extras),)
