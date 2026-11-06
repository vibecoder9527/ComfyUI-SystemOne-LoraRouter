"""Merge two decision payloads so sibling option branches can share one Aggregate."""

from __future__ import annotations

from ..aggregate import collect_decisions

CATEGORY = "SystemOne/LoraRouter"


class S1ThemeCollect:
    """Keep the first copy of each theme id. Conflicting decisions raise."""

    CATEGORY = CATEGORY
    FUNCTION = "merge"
    RETURN_TYPES = ("S1_DECISION",)
    RETURN_NAMES = ("decision",)
    OUTPUT_TOOLTIPS = (
        "Merged S1_DECISION. Wire it into another Theme, another Theme Collect, "
        "or LoRA Aggregate. Tags are recomputed from the kept decisions.",
    )
    DESCRIPTION = (
        "Join two optional S1_DECISION payloads. Use this when two option branches "
        "should apply together. a and b are both optional. One wired branch is "
        "returned unchanged. An ExecutionBlocker or missing optional input is "
        "ignored so a selected sibling can stay linked and this node can run. "
        "Zero usable inputs raises SchemaError. "
        "Order is the first copy of each theme_id: all of a, then new ids from b. "
        "The same decision for a theme_id already kept is dropped, so a shared "
        "ancestor is stored once. A different decision for that id raises SchemaError. "
        "Chain this node to merge more than two."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "a": (
                    "S1_DECISION",
                    {
                        "forceInput": True,
                        "tooltip": (
                            "First decision. Optional. Its decisions stay first. "
                            "Unconnected or blocked is ignored."
                        ),
                    },
                ),
                "b": (
                    "S1_DECISION",
                    {
                        "forceInput": True,
                        "tooltip": (
                            "Second decision. Optional. New theme ids are appended after a. "
                            "Unconnected or blocked is ignored."
                        ),
                    },
                ),
            },
        }

    def merge(self, a=None, b=None):
        return (collect_decisions(a, b),)
