"""SystemOne LoRA Router.

ComfyUI loads this file from ``custom_nodes/ComfyUI-SystemOne-LoraRouter``.
Wire LoRA Library and Theme Library into Theme Sequence, then MODEL downstream.

``S1_LORA_LIB`` and ``S1_THEME_LIB`` are custom type names. ComfyUI matches
them as strings. The sequence itself stays on the Theme Sequence widget
(``sequence_json``); it is not a wire type.

The sidebar editor is v2. This package registers widgets only.
"""

from .nodes.lora_library import S1LoraLibrary
from .nodes.theme_library import S1ThemeLibrary
from .nodes.theme_sequence import S1ThemeSequence

NODE_CLASS_MAPPINGS = {
    "S1LoraLibrary": S1LoraLibrary,
    "S1ThemeLibrary": S1ThemeLibrary,
    "S1ThemeSequence": S1ThemeSequence,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "S1LoraLibrary": "LoRA Library",
    "S1ThemeLibrary": "Theme Library",
    "S1ThemeSequence": "Theme Sequence",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
