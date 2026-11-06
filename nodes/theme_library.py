"""Theme Library node. SPEC §2.2.

Parses theme JSON into an ``S1_THEME_LIB``. Options cite ``lora_id`` only.
"""

from __future__ import annotations

from ..schema.types import EMPTY_THEME_LIBRARY_JSON, parse_theme_library

CATEGORY = "SystemOne/LoraRouter"


class S1ThemeLibrary:
    """Define themes, options, and the LoRA ids each option turns on."""

    CATEGORY = CATEGORY
    FUNCTION = "build"
    RETURN_TYPES = ("S1_THEME_LIB",)
    RETURN_NAMES = ("theme_lib",)
    DESCRIPTION = (
        "Parse a theme library JSON object into S1_THEME_LIB. "
        "select_mode single is a SystemOne choice; multi is one noul per option. "
        "Bindings store lora_id, not file paths. "
        "The S1 Editors sidebar, or the Open visual editor button, edits library_json."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "library_json": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": EMPTY_THEME_LIBRARY_JSON,
                        "dynamicPrompts": False,
                        "tooltip": (
                            'JSON object {"version": 1, "themes": [ThemeDefinition, ...]}. '
                            "The empty default is valid."
                        ),
                    },
                ),
            }
        }

    def build(self, library_json):
        return (parse_theme_library(library_json),)
