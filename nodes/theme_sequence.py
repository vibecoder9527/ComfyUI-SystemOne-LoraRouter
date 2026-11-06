"""Theme Sequence node, the main executor. SPEC §2.3 and §4.

``sequence_json`` lives on this node. There is no fourth sequence wire.
``single`` asks SystemOne ``choice``; ``multi`` asks one ``noul`` per option.
Dependencies may enable a step and rewrite its runtime copy.
``on_error=passthrough`` (the default) does not crash the graph: the input
MODEL and CLIP are returned unchanged and ``report_json`` explains the error.
"""

from __future__ import annotations

from ..schema.types import EMPTY_SEQUENCE_JSON
from ..sequence_engine import dump_report, run_sequence
from ..systemone.client import DEFAULT_ENDPOINT

CATEGORY = "SystemOne/LoraRouter"


class S1ThemeSequence:
    """Run the theme sequence and apply the selected LoRAs to MODEL."""

    CATEGORY = CATEGORY
    FUNCTION = "apply"
    RETURN_TYPES = ("MODEL", "CLIP", "STRING")
    RETURN_NAMES = ("model", "clip", "report_json")
    OUTPUT_TOOLTIPS = (
        "MODEL after LoRA weights, or the input MODEL when nothing was patched.",
        "CLIP after LoRA weights. None when the clip input was left unconnected; do not wire it downstream in that case.",
        "Compact JSON: answers, applied LoRAs, errors, and debug notes.",
    )
    DESCRIPTION = (
        "Walk sequence_json against the theme and LoRA libraries, POST to "
        "SystemOne (choice for single, noul for multi), then apply LoRAs. "
        "The API key is the api_key widget, otherwise SYSTEM_ONE_API_KEY. "
        "LoRA weights are patched with ComfyUI APIs when those are importable. "
        "on_error=passthrough returns the input MODEL and CLIP plus a debug string. "
        "The S1 Editors sidebar, or the Open visual editor button, edits sequence_json "
        "and the positive and negative prompts."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "theme_lib": ("S1_THEME_LIB", {"forceInput": True}),
                "lora_lib": ("S1_LORA_LIB", {"forceInput": True}),
                "positive": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": "Positive prompt. Sent as state.positive.",
                    },
                ),
                # Required, immediately after positive, so the node widget sits
                # under the positive prompt. A blank value is still sent as "".
                "negative": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": "Negative prompt. Sent as state.negative (empty string if blank).",
                    },
                ),
                "sequence_json": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": EMPTY_SEQUENCE_JSON,
                        "dynamicPrompts": False,
                        "tooltip": (
                            "Sequence steps and dependencies. Not a separate node output. "
                            'Default {"steps": []} is valid.'
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
                            "SystemOne bearer token. Blank falls through to the "
                            "SYSTEM_ONE_API_KEY environment variable."
                        ),
                    },
                ),
                "api_model": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "dynamicPrompts": False,
                        "tooltip": (
                            "SystemOne model name. Blank uses the skeleton fallback "
                            '"unspecified" (not a live model id).'
                        ),
                    },
                ),
            },
            "optional": {
                "clip": ("CLIP",),
                "endpoint": (
                    "STRING",
                    {
                        "default": DEFAULT_ENDPOINT,
                        "multiline": False,
                        "dynamicPrompts": False,
                        "tooltip": "SystemOne POST URL. Default https://system-one.dev/v1/systemone.",
                    },
                ),
                "noul_threshold": (
                    "FLOAT",
                    {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01},
                ),
                "on_error": (["passthrough", "raise"], {"default": "passthrough"}),
                "strength_conflict": (
                    ["max", "sum_clamp_1", "last_wins"],
                    {"default": "max"},
                ),
                "min_confidence": (
                    "FLOAT",
                    {
                        "default": 0.0,
                        "min": 0.0,
                        "max": 1.0,
                        "step": 0.01,
                        "tooltip": (
                            "When a choice confidence is below this, the choice is kept "
                            "and the report notes low_confidence_kept. An invalid choice "
                            "fails. There is no fallback option."
                        ),
                    },
                ),
            },
        }

    def apply(
        self,
        model,
        theme_lib,
        lora_lib,
        positive,
        negative="",
        sequence_json=EMPTY_SEQUENCE_JSON,
        api_key="",
        api_model="",
        clip=None,
        endpoint=DEFAULT_ENDPOINT,
        noul_threshold=0.5,
        on_error="passthrough",
        strength_conflict="max",
        min_confidence=0.0,
    ):
        try:
            result = run_sequence(
                model=model,
                clip=clip,
                lora_lib=lora_lib,
                theme_lib=theme_lib,
                sequence_json=sequence_json,
                positive=positive,
                negative=negative or "",
                api_key=api_key,
                api_model=api_model,
                endpoint=endpoint,
                noul_threshold=noul_threshold,
                on_error=on_error,
                strength_conflict=strength_conflict,
                min_confidence=min_confidence,
            )
        except Exception as exc:
            # passthrough: do not crash the graph. raise: let ComfyUI stop the run.
            if on_error == "raise":
                raise
            report = getattr(exc, "report", None)
            if not isinstance(report, dict):
                report = {
                    "answers": {},
                    "applied": [],
                    "errors": [f"{type(exc).__name__}: {exc}"],
                    "notes": [],
                    "stub": False,
                }
            else:
                report = dict(report)
                report["notes"] = list(report.get("notes") or [])
                report["errors"] = list(report.get("errors") or [])
                if not report["errors"]:
                    report["errors"].append(f"{type(exc).__name__}: {exc}")
            report.setdefault("answers", {})
            report.setdefault("applied", [])
            report["notes"].append(
                "on_error=passthrough: returning the input MODEL and CLIP unchanged."
            )
            return (model, clip, dump_report(report))
        return (result.model, result.clip, dump_report(result.report))
