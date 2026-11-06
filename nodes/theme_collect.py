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
        "Join two S1_DECISION payloads. Use this when two option branches should "
        "apply together. Order is the first copy of each theme_id: all of a, then "
        "new ids from b. The same decision for a theme_id already kept is dropped, "
        "so a shared ancestor is stored once. A different decision for that id "
        "raises SchemaError. "
        "ComfyUI does not run this node when either input is an ExecutionBlocker. "
        "Both branches have to emit a payload. Chain this node to merge more than two."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "a": (
                    "S1_DECISION",
                    {
                        "forceInput": True,
                        "tooltip": "First decision. Its decisions stay first.",
                    },
                ),
                "b": (
                    "S1_DECISION",
                    {
                        "forceInput": True,
                        "tooltip": "Second decision. New theme ids are appended after a.",
                    },
                ),
            }
        }

    def merge(self, a, b):
        return (collect_decisions(a, b),)
