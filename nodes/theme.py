"""One Theme node: SystemOne decision, tags, and an upstream enable chain."""

from __future__ import annotations

from ..schema.types import EMPTY_ENABLE_JSON, EMPTY_THEME_JSON
from ..systemone.client import DEFAULT_ENDPOINT
from ..theme_engine import dump_report, run_theme

CATEGORY = "SystemOne/LoraRouter"


class S1Theme:
    """Ask SystemOne about one theme, or skip it when it is not enabled."""

    CATEGORY = CATEGORY
    FUNCTION = "decide"
    RETURN_TYPES = ("S1_THEME_RESULT", "STRING")
    RETURN_NAMES = ("theme_result", "report_json")
    OUTPUT_TOOLTIPS = (
        "Accumulated decisions and tags. Wire this into another Theme's upstream or into LoRA Aggregate.",
        "Compact JSON for this decision and the upstream chain. It does not contain the API key.",
    )
    DESCRIPTION = (
        "One theme. Options contribute tags; they do not store LoRA bindings. "
        "run=disabled (the default) does not call SystemOne and adds no tags. "
        "run=enabled is an explicit root. run=when_upstream turns the theme on "
        "only when enable_json matches selected options on the upstream result. "
        "single is a SystemOne choice; multi is one noul per option. "
        "The API key is the api_key widget, otherwise SYSTEM_ONE_API_KEY. "
        "on_error=passthrough records the failure and keeps upstream tags. "
        "Open visual editor opens a modal that edits theme_json, enable_json, "
        "and the positive and negative prompts."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "positive": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": "Positive prompt. Sent as state.positive.",
                    },
                ),
                "negative": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": "Negative prompt, directly under positive. Sent as state.negative.",
                    },
                ),
                "theme_json": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": EMPTY_THEME_JSON,
                        "dynamicPrompts": False,
                        "tooltip": (
                            "One theme: theme_id, title, instructions, select_mode, "
                            "options with tags, optional none_option_id."
                        ),
                    },
                ),
                "run": (
                    ["disabled", "enabled", "when_upstream"],
                    {
                        "default": "disabled",
                        "tooltip": (
                            "disabled: no API call. enabled: always decide. "
                            "when_upstream: decide only when enable_json matches."
                        ),
                    },
                ),
                "enable_json": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": EMPTY_ENABLE_JSON,
                        "dynamicPrompts": False,
                        "tooltip": (
                            "Clauses target an upstream theme_id and option ids. "
                            "Used only when run is when_upstream. An empty clause list matches nothing."
                        ),
                    },
                ),
                "api_key": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "dynamicPrompts": False,
                        "tooltip": (
                            "SystemOne bearer token. A non-empty widget wins over "
                            "SYSTEM_ONE_API_KEY. Ignored when this theme does not call the API."
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
            },
            "optional": {
                "upstream": (
                    "S1_THEME_RESULT",
                    {
                        "forceInput": True,
                        "tooltip": "Accumulated result from an upstream Theme or Theme Collect.",
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
                    {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01},
                ),
                "on_error": (["passthrough", "raise"], {"default": "passthrough"}),
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
            },
        }

    def decide(
        self,
        positive,
        negative,
        theme_json,
        run,
        enable_json,
        api_key,
        api_model,
        upstream=None,
        endpoint=DEFAULT_ENDPOINT,
        noul_threshold=0.5,
        on_error="passthrough",
        min_confidence=0.0,
    ):
        outcome = run_theme(
            theme_json=theme_json,
            positive=positive,
            negative=negative or "",
            run=run,
            enable_json=enable_json,
            upstream=upstream,
            api_key=api_key,
            api_model=api_model,
            endpoint=endpoint,
            noul_threshold=noul_threshold,
            on_error=on_error,
            min_confidence=min_confidence,
        )
        return (outcome.result, dump_report(outcome.report))
