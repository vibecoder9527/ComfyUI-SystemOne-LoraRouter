"""Merge two theme results so a branch can feed LoRA Aggregate."""

from __future__ import annotations

from ..aggregate import collect_theme_results

CATEGORY = "SystemOne/LoraRouter"


class S1ThemeCollect:
    """Append result b after result a. Identical theme ids collapse once."""

    CATEGORY = CATEGORY
    FUNCTION = "merge"
    RETURN_TYPES = ("S1_THEME_RESULT",)
    RETURN_NAMES = ("theme_result",)
    OUTPUT_TOOLTIPS = (
        "First copy of each theme id from a, then ids that appear only in b. "
        "Tags are recomputed from the kept decisions.",
    )
    DESCRIPTION = (
        "Join two S1_THEME_RESULT values. Wire the output into another Theme's "
        "upstream input, another Theme Collect, or LoRA Aggregate. "
        "Order is the first copy of each theme_id: all of a, then new ids from b. "
        "The same decision for a theme_id already kept is dropped, so two branches "
        "that share an ancestor merge that ancestor once. A different decision for "
        "that id raises SchemaError and is not overwritten. "
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
