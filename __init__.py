"""SystemOne LoRA Router.

ComfyUI loads this file from ``custom_nodes/ComfyUI-SystemOne-LoraRouter``.

Wire one or more Theme nodes into a chain, or merge branches with Theme
Collect. Collect keeps one copy of an identical shared decision and raises
when the same theme id disagrees. Wire the final ``S1_THEME_RESULT`` and a
LoRA Library into LoRA Aggregate with MODEL. Themes default to disabled. A
root sets ``run`` to ``enabled``. A downstream theme sets ``run`` to
``when_upstream`` and targets upstream option ids in ``enable_json``.
The browser extension writes a free ``theme_N`` onto new and duplicated
Theme nodes before queue. A unique saved id is left as stored.

``S1_LORA_LIB`` and ``S1_THEME_RESULT`` are custom type names. ComfyUI matches
them as strings.

``js/`` is the visual editor. It opens a modal from the node. It does not
register a sidebar tab. The editor reads and writes the same JSON widgets.
"""

from .nodes.lora_aggregate import S1LoraAggregate
from .nodes.lora_library import S1LoraLibrary
from .nodes.theme import S1Theme
from .nodes.theme_collect import S1ThemeCollect

NODE_CLASS_MAPPINGS = {
    "S1LoraLibrary": S1LoraLibrary,
    "S1Theme": S1Theme,
    "S1ThemeCollect": S1ThemeCollect,
    "S1LoraAggregate": S1LoraAggregate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "S1LoraLibrary": "LoRA Library",
    "S1Theme": "Theme",
    "S1ThemeCollect": "Theme Collect",
    "S1LoraAggregate": "LoRA Aggregate",
}

# ComfyUI serves every .js file in this directory as a frontend extension.
WEB_DIRECTORY = "./js"

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]
