"""SystemOne LoRA Router.

ComfyUI loads this file from ``custom_nodes/ComfyUI-SystemOne-LoraRouter``.

Wire SystemOne Settings into Theme Root and into each downstream Theme.
Positive is the prompt socket above negative. Negative is optional;
unconnected or blank is sent as empty. Theme Root always decides.
Each option in ``theme_json`` is an output slot. Wire the slot you care
about into a child Theme's ``upstream`` input, or into LoRA Aggregate.
An unselected slot is an ExecutionBlocker, so the nodes on that wire do
not run. Theme Collect merges optional ``S1_DECISION`` payloads when sibling
branches should apply together. One wired branch is returned unchanged.

``S1_SETTINGS``, ``S1_DECISION``, and ``S1_LORA_LIB`` are custom type names.
ComfyUI matches them as strings.

``js/`` is the visual editor. It opens a modal from the node. It does not
register a sidebar tab. The editor writes ``theme_json`` on Theme Root and
Theme, and ``library_json`` on LoRA Library. Prompts are not theme fields.
The browser extension writes a free ``theme_N`` onto new and duplicated
theme nodes before queue. A unique saved id is left as stored.
"""

from .nodes.lora_aggregate import S1LoraAggregate
from .nodes.lora_library import S1LoraLibrary
from .nodes.settings import S1Settings
from .nodes.theme import S1Theme, S1ThemeRoot
from .nodes.theme_collect import S1ThemeCollect

NODE_CLASS_MAPPINGS = {
    "S1LoraLibrary": S1LoraLibrary,
    "S1Settings": S1Settings,
    "S1ThemeRoot": S1ThemeRoot,
    "S1Theme": S1Theme,
    "S1ThemeCollect": S1ThemeCollect,
    "S1LoraAggregate": S1LoraAggregate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "S1LoraLibrary": "LoRA Library",
    "S1Settings": "SystemOne Settings",
    "S1ThemeRoot": "Theme Root",
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
