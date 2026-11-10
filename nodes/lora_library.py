"""LoRA Library node.

Parses library JSON into an ``S1_LORA_LIB``. Does not read weight files.
"""

from __future__ import annotations

from ..schema.types import EMPTY_LORA_LIBRARY_JSON, parse_lora_library

CATEGORY = "SystemOne/LoraRouter"


class S1LoraLibrary:
    """Define LoRA ids, file names, strengths, and tags."""

    CATEGORY = CATEGORY
    FUNCTION = "build"
    RETURN_TYPES = ("S1_LORA_LIB",)
    RETURN_NAMES = ("lora_lib",)
    DESCRIPTION = (
        "Parse a LoRA library JSON object into S1_LORA_LIB. "
        "Stores the file name under ComfyUI loras/, tags, strengths, and an optional Slider flag. "
        "Slider entries allow negative strength in the -5 to 5 range. Library tags stay plain names. "
        "Does not load the weight file. "
        "Open visual editor opens a modal that edits library_json. "
        "Its name field can pick a file from the ComfyUI loras list; typed names still work."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "library_json": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": EMPTY_LORA_LIBRARY_JSON,
                        "dynamicPrompts": False,
                        "tooltip": (
                            'JSON object {"version": 1, "loras": [LoraEntry, ...]}. '
                            "The empty default is valid. Tags are matched by LoRA Aggregate."
                        ),
                    },
                ),
            }
        }

    def build(self, library_json):
        return (parse_lora_library(library_json),)
