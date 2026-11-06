"""Theme Root and Theme. Each option is an output slot.

Theme Root always decides. A downstream Theme decides when its ``upstream``
input is a real ``S1_DECISION``. An unselected parent slot is an
``ExecutionBlocker``, and ComfyUI does not run the nodes wired only to it.

Outputs are ``MAX_OPTION_OUTPUTS`` sockets of type ``S1_DECISION`` plus
``report_json`` at the last index. Slot ``i`` is ``theme.options[i]``. Slots
past the option list are blockers. The frontend renames and hides them.
"""

from __future__ import annotations

from ..schema.blocker import execution_blocker, is_execution_blocker
from ..schema.types import (
    MAX_OPTION_OUTPUTS,
    REPORT_OUTPUT_INDEX,
    DecisionPayload,
    RouterSettings,
    SchemaError,
    parse_theme,
)
from ..theme_engine import dump_report, option_slot_values, run_theme

CATEGORY = "SystemOne/LoraRouter"

_OPTION_TYPES = ("S1_DECISION",) * MAX_OPTION_OUTPUTS + ("STRING",)
_OPTION_NAMES = tuple(f"option_{index + 1}" for index in range(MAX_OPTION_OUTPUTS)) + (
    "report_json",
)
_OPTION_TOOLTIPS = tuple(
    f"Option slot {index + 1}. Carries accumulated tags when that option is selected. "
    "An unselected slot is an ExecutionBlocker and does not run downstream nodes."
    for index in range(MAX_OPTION_OUTPUTS)
) + (
    "Compact JSON for this decision. It does not contain the API key. "
    f"This socket stays at output index {REPORT_OUTPUT_INDEX}.",
)


def _blocked_outputs(note: str) -> tuple:
    report = {
        "role": "downstream",
        "status": "blocked",
        "enabled": False,
        "selected": [],
        "tags": [],
        "decisions": [],
        "accumulated_tags": [],
        "errors": [],
        "slots": [],
        "api": {
            "called": False,
            "endpoint": "",
            "model": "",
            "key_source": "missing",
            "stub": False,
        },
        "notes": [note],
    }
    blocked = tuple(execution_blocker(None) for _ in range(MAX_OPTION_OUTPUTS))
    return blocked + (dump_report(report),)


def _pack(theme, outcome) -> tuple:
    if not theme.options and outcome.result.errors:
        outcome.report.setdefault("notes", []).append(
            "This theme has no option slots, so nothing downstream of this node runs."
        )
    values = option_slot_values(theme, outcome.result)
    own = outcome.result.get(theme.theme_id)
    if theme.options and outcome.report.get("status") == "ok" and own is not None and not own.selected:
        outcome.report.setdefault("notes", []).append(
            "No option was selected, so every option slot is blocked. "
            "Upstream tags stay on this result but are not emitted on a slot."
        )
    emitted = []
    for option, value in zip(theme.options, values):
        if is_execution_blocker(value):
            kind = "blocked"
        else:
            kind = value.emitted_reason
        emitted.append({"option_id": option.option_id, "emitted": kind})
    outcome.report["slots"] = emitted
    padded = list(values) + [execution_blocker(None)] * (MAX_OPTION_OUTPUTS - len(values))
    return tuple(padded) + (dump_report(outcome.report),)


class _ThemeOutputs:
    """Shared outputs. Subclasses supply inputs and ``decide``."""

    CATEGORY = CATEGORY
    FUNCTION = "decide"
    RETURN_TYPES = _OPTION_TYPES
    RETURN_NAMES = _OPTION_NAMES
    OUTPUT_TOOLTIPS = _OPTION_TOOLTIPS

    def _run(self, positive, negative, settings, theme_json, upstream_result, role):
        if not isinstance(settings, RouterSettings):
            raise SchemaError("settings must be an S1_SETTINGS from SystemOne Settings")
        theme = parse_theme(theme_json)
        if len(theme.options) > MAX_OPTION_OUTPUTS:
            raise SchemaError(
                f"theme {theme.theme_id!r} has {len(theme.options)} options; "
                f"option outputs are capped at {MAX_OPTION_OUTPUTS}"
            )
        outcome = run_theme(
            theme_json=theme_json,
            positive=positive,
            negative=negative or "",
            settings=settings,
            upstream=upstream_result,
            role=role,
        )
        return _pack(theme, outcome)


class S1ThemeRoot(_ThemeOutputs):
    """Always decide. Wire one option slot into a child Theme or into Aggregate."""

    DESCRIPTION = (
        "Root theme. It always asks SystemOne when the theme has a decision to make. "
        "Positive is the input above negative. Both are sockets, not body text. "
        "Settings comes from SystemOne Settings. There is no run switch, no enable_json, "
        "and no API widgets on this node. "
        "Each option in theme_json is an output slot, in that order. "
        "The selected slot carries accumulated tags. Unselected slots are ExecutionBlockers. "
        "none_option_id contributes no tags when it is chosen, and its slot still emits. "
        "Open visual editor edits theme_json only. Invalid drafts are not written."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "positive": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Positive prompt. The input above negative. Sent as state.positive.",
                    },
                ),
                "negative": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Negative prompt, below positive. Sent as state.negative. Blank is empty.",
                    },
                ),
                "settings": (
                    "S1_SETTINGS",
                    {
                        "forceInput": True,
                        "tooltip": "SystemOne Settings. API key, endpoint, and on_error live there.",
                    },
                ),
                "theme_json": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": _empty_theme(),
                        "dynamicPrompts": False,
                        "tooltip": (
                            "One theme: theme_id, title, instructions, select_mode, "
                            "options with tags, optional none_option_id. "
                            "Option order is output-slot order. Prompts are not stored here."
                        ),
                    },
                ),
            }
        }

    def decide(self, positive, negative, settings, theme_json):
        return self._run(positive, negative, settings, theme_json, None, "root")


class S1Theme(_ThemeOutputs):
    """Decide because a parent option slot fired. That wire replaces enable_json."""

    DESCRIPTION = (
        "Downstream theme. It runs when upstream is an S1_DECISION from a parent "
        "option slot or from Theme Collect. An ExecutionBlocker upstream does not "
        "call SystemOne and blocks every output of this node. "
        "Positive is the input above negative. Settings comes from SystemOne Settings. "
        "There is no run switch, no enable_json, and no API widgets. "
        "Option slots follow theme_json order. "
        "Open visual editor edits theme_json only."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "positive": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Positive prompt. The input above negative. Not copied from the parent theme.",
                    },
                ),
                "negative": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Negative prompt, below positive. Blank is sent as empty.",
                    },
                ),
                "settings": (
                    "S1_SETTINGS",
                    {
                        "forceInput": True,
                        "tooltip": "SystemOne Settings. Share the root's settings node or use another.",
                    },
                ),
                "upstream": (
                    "S1_DECISION",
                    {
                        "forceInput": True,
                        "tooltip": (
                            "A parent option slot, or Theme Collect. "
                            "Wiring this input is what used to be enable_json."
                        ),
                    },
                ),
                "theme_json": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": _empty_theme(),
                        "dynamicPrompts": False,
                        "tooltip": (
                            "One theme. Option order is output-slot order. "
                            "Prompts are not stored in this JSON."
                        ),
                    },
                ),
            }
        }

    def decide(self, positive, negative, settings, theme_json, upstream):
        if is_execution_blocker(upstream):
            return _blocked_outputs(
                "Upstream option slot did not run. SystemOne was not called and this theme added no tags."
            )
        if not isinstance(upstream, DecisionPayload):
            raise SchemaError(
                "upstream must be an S1_DECISION from a parent option slot or Theme Collect"
            )
        return self._run(
            positive,
            negative,
            settings,
            theme_json,
            upstream.result,
            "downstream",
        )


def _empty_theme() -> str:
    from ..schema.types import EMPTY_THEME_JSON

    return EMPTY_THEME_JSON
