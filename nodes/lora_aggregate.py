"""Apply each tag-matched LoRA once to MODEL and optional CLIP."""

from __future__ import annotations

from ..aggregate import aggregate_loras
from ..schema.types import SchemaError
from ..theme_engine import dump_report

CATEGORY = "SystemOne/LoraRouter"


class S1LoraAggregate:
    """Dedupe library LoRAs by id and patch weights with apply_loras."""

    CATEGORY = CATEGORY
    FUNCTION = "apply"
    RETURN_TYPES = ("MODEL", "CLIP", "STRING")
    RETURN_NAMES = ("model", "clip", "report_json")
    OUTPUT_TOOLTIPS = (
        "MODEL after each matched LoRA is applied once, or the input MODEL when nothing was patched.",
        "CLIP after those LoRAs. None when clip was left unconnected.",
        "Tags, theme decisions, matched LoRAs, apply errors, and notes.",
    )
    DESCRIPTION = (
        "Match S1_LORA_LIB tags to the tags on an S1_DECISION. "
        "Wire decision from a selected option slot or from Theme Collect. "
        "enabled_default true always applies; false applies only when a tag name overlaps "
        "(case-insensitive, ignoring an optional :weight on the option tag). "
        "A weighted option tag overrides both strengths; weight 0 skips that LoRA. "
        "Each lora_id is applied once, in lora_id order. "
        "on_error here is weight loading, not the theme's SystemOne on_error. "
        "passthrough returns the input MODEL and CLIP when the inputs are unusable "
        "or a weight file fails. Theme errors already stored on the decision "
        "do not cancel tags that upstream themes contributed."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "lora_lib": ("S1_LORA_LIB", {"forceInput": True}),
                "decision": (
                    "S1_DECISION",
                    {
                        "forceInput": True,
                        "tooltip": "Selected option slot or Theme Collect. Carries accumulated tags.",
                    },
                ),
            },
            "optional": {
                "clip": ("CLIP",),
                "on_error": (["passthrough", "raise"], {"default": "passthrough"}),
            },
        }

    def apply(self, model, lora_lib, decision, clip=None, on_error="passthrough"):
        try:
            outcome = aggregate_loras(
                model=model,
                clip=clip,
                lora_lib=lora_lib,
                decision=decision,
                on_error=on_error,
            )
        except SchemaError as exc:
            if on_error == "raise":
                raise
            report = {
                "tags": [],
                "themes": [],
                "matched": [],
                "skipped": [],
                "applied": [],
                "errors": [str(exc)],
                "notes": [
                    "on_error=passthrough: returning the input MODEL and CLIP unchanged."
                ],
            }
            return (model, clip, dump_report(report))
        return (outcome.model, outcome.clip, dump_report(outcome.report))
