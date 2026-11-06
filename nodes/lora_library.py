"""LoRA Library node. SPEC §2.1.

Parses library JSON into an ``S1_LORA_LIB``. Does not read ``.safetensors``.
"""

from __future__ import annotations

from ..schema.types import EMPTY_LORA_LIBRARY_JSON, parse_lora_library

CATEGORY = "SystemOne/LoraRouter"


class S1LoraLibrary:
    """Define the LoRA ids Theme Sequence is allowed to apply."""

    CATEGORY = CATEGORY
    FUNCTION = "build"
    RETURN_TYPES = ("S1_LORA_LIB",)
    RETURN_NAMES = ("lora_lib",)
    DESCRIPTION = (
        "Parse a LoRA library JSON object into S1_LORA_LIB. "
        "Stores the file name under ComfyUI loras/ and the default strengths. "
        "Does not load the weight file. "
        "The S1 Editors sidebar, or the Open visual editor button, edits library_json. "
        "Its name field can pick a file from the ComfyUI loras list; typed names still work."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # dynamicPrompts off: the default value is JSON and contains braces.
                "library_json": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": EMPTY_LORA_LIBRARY_JSON,
                        "dynamicPrompts": False,
                        "tooltip": (
                            'JSON object {"version": 1, "loras": [LoraEntry, ...]}. '
                            "The empty default is valid."
                        ),
                    },
                ),
            }
        }

    def build(self, library_json):
        return (parse_lora_library(library_json),)
