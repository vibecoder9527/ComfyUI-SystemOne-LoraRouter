"""SystemOne Settings: endpoint, key, model, and error policy for Theme nodes."""

from __future__ import annotations

from ..schema.types import build_settings
from ..systemone.client import DEFAULT_ENDPOINT

CATEGORY = "SystemOne/LoraRouter"


class S1Settings:
    """One settings object shared by every theme on the graph."""

    CATEGORY = CATEGORY
    FUNCTION = "build"
    RETURN_TYPES = ("S1_SETTINGS",)
    RETURN_NAMES = ("settings",)
    OUTPUT_TOOLTIPS = (
        "API endpoint, key, model, noul threshold, on_error, and min confidence. "
        "Wire this into Theme Root and Theme. The key is not written into reports.",
    )
    DESCRIPTION = (
        "Holds the SystemOne API settings that used to sit on each Theme. "
        "api_key wins over SYSTEM_ONE_API_KEY when it is non-empty. "
        "A blank api_model is sent as unspecified. "
        "on_error is passthrough or raise for theme decisions. "
        "LoRA Aggregate has its own on_error for weight files. "
        "This node does not call SystemOne."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_key": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "dynamicPrompts": False,
                        "tooltip": (
                            "SystemOne bearer token. A non-empty value wins over "
                            "SYSTEM_ONE_API_KEY. It is not copied into report_json."
                        ),
                    },
                ),
                "api_model": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "dynamicPrompts": False,
                        "tooltip": 'SystemOne model name. Blank becomes "unspecified".',
                    },
                ),
                "endpoint": (
                    "STRING",
                    {
                        "default": DEFAULT_ENDPOINT,
                        "multiline": False,
                        "dynamicPrompts": False,
                        "tooltip": "SystemOne POST URL.",
                    },
                ),
                "noul_threshold": (
                    "FLOAT",
                    {
                        "default": 0.5,
                        "min": 0.0,
                        "max": 1.0,
                        "step": 0.01,
                        "tooltip": "A multi option is selected when its noul score is at least this.",
                    },
                ),
                "on_error": (
                    ["passthrough", "raise"],
                    {
                        "default": "passthrough",
                        "tooltip": (
                            "passthrough records the API or choice failure, adds no tags, "
                            "and still emits the accumulated payload on every option slot. "
                            "raise stops the graph."
                        ),
                    },
                ),
                "min_confidence": (
                    "FLOAT",
                    {
                        "default": 0.0,
                        "min": 0.0,
                        "max": 1.0,
                        "step": 0.01,
                        "tooltip": (
                            "When a choice confidence is below this, the choice is kept. "
                            "An invalid choice fails. There is no fallback option."
                        ),
                    },
                ),
            }
        }

    def build(
        self,
        api_key,
        api_model,
        endpoint=DEFAULT_ENDPOINT,
        noul_threshold=0.5,
        on_error="passthrough",
        min_confidence=0.0,
    ):
        return (
            build_settings(
                api_key=api_key,
                api_model=api_model,
                endpoint=endpoint,
                noul_threshold=noul_threshold,
                on_error=on_error,
                min_confidence=min_confidence,
            ),
        )
