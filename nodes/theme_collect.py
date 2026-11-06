"""Merge two theme results so a branch can feed LoRA Aggregate."""

from __future__ import annotations

from ..aggregate import collect_theme_results

CATEGORY = "SystemOne/LoraRouter"


class S1ThemeCollect:
    """Append result b after result a. Duplicate theme ids raise."""

    CATEGORY = CATEGORY
    FUNCTION = "merge"
    RETURN_TYPES = ("S1_THEME_RESULT",)
    RETURN_NAMES = ("theme_result",)
    OUTPUT_TOOLTIPS = (
        "Decisions from a, then decisions from b. Tags are recomputed in that order.",
    )
    DESCRIPTION = (
        "Join two S1_THEME_RESULT chains. Wire the output into another Theme's "
        "upstream input, another Theme Collect, or LoRA Aggregate. "
        "Order is a then b. A repeated theme_id raises; it is not overwritten. "
        "Chain this node to merge more than two results."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "a": (
                    "S1_THEME_RESULT",
                    {"forceInput": True, "tooltip": "First result. Its decisions stay first."},
                ),
                "b": (
                    "S1_THEME_RESULT",
                    {"forceInput": True, "tooltip": "Second result. Appended after a."},
                ),
            }
        }

    def merge(self, a, b):
        return (collect_theme_results(a, b),)
