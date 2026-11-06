"""Theme Sequence executor (SPEC §4).

Control flow:

- ``select_mode: single`` sends one SystemOne question of type ``choice``.
- ``select_mode: multi`` sends one ``noul`` question per option. A score at or
  above ``noul_threshold`` selects that option. More than 32 options are split
  across requests that share the same state.
- Dependencies are OR: every matching ``when`` runs its ``actions`` in order.
  ``enable_step`` / ``disable_step`` / ``rewrite_*`` edit a runtime copy of the
  theme. The Theme Library object is not modified.
- A step that is disabled after dependencies is ``skipped`` and does not call
  SystemOne. Later steps can match ``when.op: skipped``.
- One option left on a single-select step skips the API and takes that option
  (SPEC §4.2.1). This runner does not invent an extra ``__none__`` option.
- API and decision failures raise ``SequenceError`` with a partial report.
  ``S1ThemeSequence`` turns that into an unchanged MODEL/CLIP when
  ``on_error`` is ``passthrough``. Missing LoRA files are handled in
  ``apply_loras`` (skip on passthrough, raise on raise).
- ``SystemOneClient.decide`` POSTs JSON. A missing API key raises
  ``SystemOneError`` when a live call is made (mapped here via ``on_error``).
  Injected test clients may override ``decide``.
- LoRA weights are patched with ComfyUI APIs when those imports work. Outside
  ComfyUI, ``apply_loras`` leaves MODEL and CLIP unchanged.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any

from .apply_loras import apply_loras
from .schema.types import (
    Action,
    LoraLibrary,
    SchemaError,
    ThemeDefinition,
    ThemeLibrary,
    WhenClause,
    parse_sequence,
    validate_refs,
)
from .systemone.client import (
    DEFAULT_ENDPOINT,
    SystemOneClient,
    SystemOneError,
    resolve_api_key,
    resolve_model_name,
)

# SPEC §4.2.2. One noul question per option; the official cap is 32 per POST.
NOUL_BATCH = 32
NOUL_TRUE = "提示詞明確需要或強烈暗示此選項"
NOUL_FALSE = "提示詞不需要此選項"

_ON_ERROR = {"passthrough", "raise"}
_STRENGTH = {"max", "sum_clamp_1", "last_wins"}


class SequenceError(RuntimeError):
    """The run stopped before LoRAs were patched. `report` is safe to show."""

    def __init__(self, message: str, report: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.report = report


@dataclass
class RunResult:
    model: Any
    clip: Any
    report: dict[str, Any] = field(default_factory=dict)


def dump_report(report: dict[str, Any]) -> str:
    """Compact JSON. Non-ASCII (theme text in notes) stays readable."""

    return json.dumps(report, ensure_ascii=False, separators=(",", ":"))


def run_sequence(
    *,
    model: Any,
    clip: Any,
    lora_lib: LoraLibrary,
    theme_lib: ThemeLibrary,
    sequence_json: str | dict[str, Any],
    positive: str,
    negative: str = "",
    api_key: str = "",
    api_model: str = "",
    endpoint: str = DEFAULT_ENDPOINT,
    noul_threshold: float = 0.5,
    on_error: str = "passthrough",
    strength_conflict: str = "max",
    min_confidence: float = 0.0,
    client: SystemOneClient | None = None,
) -> RunResult:
    """Walk `sequence_json` and return the patched model plus a report.

    Schema and SystemOne errors propagate as ``SchemaError`` or
    ``SequenceError``. The node wrapper catches them when ``on_error`` is
    ``passthrough``. ``apply_loras`` applies ``on_error`` itself for missing files.
    """

    if not isinstance(positive, str):
        raise SchemaError("positive must be a string")
    if not isinstance(negative, str):
        raise SchemaError("negative must be a string")
    if on_error not in _ON_ERROR:
        raise SchemaError(f"on_error must be one of: {', '.join(sorted(_ON_ERROR))}")
    if strength_conflict not in _STRENGTH:
        raise SchemaError(
            f"strength_conflict must be one of: {', '.join(sorted(_STRENGTH))}"
        )
    threshold = _unit_float("noul_threshold", noul_threshold)
    confidence_floor = _unit_float("min_confidence", min_confidence)
    endpoint = (endpoint or "").strip() or DEFAULT_ENDPOINT
    if not (endpoint.startswith("https://") or endpoint.startswith("http://")):
        raise SchemaError("endpoint must start with http:// or https://")

    if not isinstance(lora_lib, LoraLibrary):
        raise SchemaError("lora_lib must be an S1_LORA_LIB from S1LoraLibrary")
    if not isinstance(theme_lib, ThemeLibrary):
        raise SchemaError("theme_lib must be an S1_THEME_LIB from S1ThemeLibrary")

    sequence = parse_sequence(sequence_json)
    validate_refs(sequence, theme_lib, lora_lib)

    key, key_source = resolve_api_key(api_key)
    model_name = resolve_model_name(api_model)
    if client is None:
        client = SystemOneClient(api_key=key, endpoint=endpoint, model=model_name)

    # SPEC §4.1. state is an object. An empty negative is still "".
    state = {"positive": positive, "negative": negative}
    answers: dict[str, dict[str, Any]] = {}
    pending: dict[str, dict[str, Any]] = {}
    step_enabled = {step.step_id: step.enabled_by_default for step in sequence.steps}
    notes: list[str] = []
    if getattr(client, "IS_STUB", False):
        notes.append(
            "SystemOne client is a stub; decide() did not send HTTP."
        )
    if key_source == "missing":
        notes.append(
            "api_key is empty (widget blank and SYSTEM_ONE_API_KEY unset). "
            "A live SystemOne call requires a key."
        )

    def fail(message: str) -> None:
        report = _report(
            answers=answers,
            applied=[],
            errors=[message],
            notes=notes,
            client=client,
            endpoint=endpoint,
            model_name=model_name,
            key_source=key_source,
        )
        raise SequenceError(message, report)

    for step in sequence.steps:
        try:
            # Runtime copy: rewrite must not change the Theme Library the node returned.
            runtime = copy.deepcopy(theme_lib.themes[step.theme_id])
            # OR: each dependency whose when matches runs its actions, in list order.
            # Actions see only steps that already have an answer.
            for dependency in step.dependencies:
                if _when_matches(dependency.when, answers):
                    for action in dependency.actions:
                        _apply_action(action, step.step_id, step_enabled, runtime)
            if not step_enabled[step.step_id]:
                answers[step.step_id] = {"status": "skipped"}
                continue
            if not runtime.options:
                fail(f"step {step.step_id!r} has no options after dependency rewrite")
            if runtime.select_mode == "single":
                selected, raw = _run_single(
                    client, state, step.step_id, runtime, confidence_floor, fail
                )
            elif runtime.select_mode == "multi":
                # multi → one noul per option, batched at 32.
                selected, raw = _run_multi(
                    client, state, step.step_id, runtime, threshold, fail
                )
            else:
                fail(
                    f"step {step.step_id!r} has select_mode {runtime.select_mode!r}; "
                    "expected single or multi"
                )
            _accumulate(
                pending, selected, runtime, lora_lib, step.step_id, strength_conflict, fail
            )
            answers[step.step_id] = {"status": "ok", "selected": selected, "raw": raw}
        except SequenceError:
            raise
        except SchemaError as exc:
            fail(str(exc))
        except SystemOneError as exc:
            fail(f"SystemOne: {exc}")
        except Exception as exc:
            fail(f"{type(exc).__name__}: {exc}")

    ordered = [_public_pending(pending[lora_id]) for lora_id in sorted(pending)]
    outcome = apply_loras(model, clip, ordered, on_error=on_error)
    notes.extend(outcome.notes)
    report = _report(
        answers=answers,
        applied=outcome.applied,
        errors=list(outcome.errors),
        notes=notes,
        client=client,
        endpoint=endpoint,
        model_name=model_name,
        key_source=key_source,
    )
    return RunResult(model=outcome.model, clip=outcome.clip, report=report)


def _run_single(client, state, step_id, theme: ThemeDefinition, min_confidence, fail):
    # SPEC §4.2.1: a single remaining option skips the API and is selected.
    if len(theme.options) == 1:
        only = theme.options[0].option_id
        return [only], {"skipped_api": True, "reason": "single_option", "choice": only}

    questions = {
        step_id: {
            "type": "choice",
            "instructions": theme.instructions,
            "criteria": {option.option_id: option.description for option in theme.options},
        }
    }
    response = _call(client, state, questions, fail)
    raw_answer = response["answers"].get(step_id)
    if not isinstance(raw_answer, dict) or "choice" not in raw_answer:
        fail(f"SystemOne choice response for step {step_id!r} has no choice")
    choice = raw_answer.get("choice")
    valid = {option.option_id for option in theme.options}
    reason = None
    confidence = raw_answer.get("confidence")
    if choice not in valid:
        choice, reason = _fallback_or_fail(
            theme,
            valid,
            fail,
            f"step {step_id!r} got choice {choice!r}, which is not an option",
        )
    elif confidence is not None and _as_confidence(confidence, step_id, fail) < min_confidence:
        # SPEC §2.3: choice below min_confidence uses fallback_option_id when set.
        if theme.fallback_option_id:
            choice, reason = _fallback_or_fail(
                theme,
                valid,
                fail,
                f"step {step_id!r} confidence {confidence} is below {min_confidence}",
            )
        else:
            reason = "low_confidence_kept"
    raw = {"stub": response.get("stub", False), "answers": {step_id: raw_answer}}
    if reason:
        raw["decision"] = reason
    return [choice], raw


def _run_multi(client, state, step_id, theme: ThemeDefinition, threshold, fail):
    questions = {}
    for option in theme.options:
        qid = f"{step_id}__{option.option_id}"
        questions[qid] = {
            "type": "noul",
            "instructions": (
                f"{theme.instructions}\n"
                f"具體選項：{option.label} — {option.description}\n"
                "是否應啟用此選項？"
            ),
            "criteria": {"true": NOUL_TRUE, "false": NOUL_FALSE},
        }
    items = list(questions.items())
    merged: dict[str, Any] = {}
    stub = True
    for start in range(0, len(items), NOUL_BATCH):
        chunk = dict(items[start : start + NOUL_BATCH])
        response = _call(client, state, chunk, fail)
        stub = stub and bool(response.get("stub", False))
        for qid in chunk:
            answer = response["answers"].get(qid)
            if not isinstance(answer, dict) or "noul" not in answer:
                fail(f"SystemOne noul response for {qid!r} has no noul")
            score = answer["noul"]
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                fail(f"SystemOne noul for {qid!r} is not a number")
            merged[qid] = {"noul": float(score)}
    selected = []
    for option in theme.options:
        qid = f"{step_id}__{option.option_id}"
        if merged[qid]["noul"] >= threshold:
            selected.append(option.option_id)
    return selected, {"stub": stub, "answers": merged}


def _call(client, state, questions, fail) -> dict[str, Any]:
    try:
        response = client.decide(state, questions)
    except SystemOneError as exc:
        fail(f"SystemOne: {exc}")
    except SequenceError:
        raise
    except Exception as exc:
        fail(f"SystemOne: {type(exc).__name__}: {exc}")
    if not isinstance(response, dict) or not isinstance(response.get("answers"), dict):
        fail("SystemOne response is missing an answers object")
    missing = [qid for qid in questions if qid not in response["answers"]]
    if missing:
        fail(f"SystemOne response is missing answers for {missing!r}")
    return response


def _fallback_or_fail(theme: ThemeDefinition, valid: set[str], fail, message: str):
    fallback = theme.fallback_option_id
    if not fallback:
        fail(message)
    if fallback not in valid:
        fail(
            f"{message}; fallback_option_id {fallback!r} is not in the runtime options"
        )
    return fallback, "used_fallback"


def _as_confidence(value, step_id: str, fail) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        fail(f"step {step_id!r} confidence is not a number")
    return float(value)


def _accumulate(pending, selected, theme, lora_lib, step_id, policy, fail) -> None:
    by_id = {option.option_id: option for option in theme.options}
    for option_id in selected:
        option = by_id.get(option_id)
        if option is None:
            fail(f"step {step_id!r} selected unknown option {option_id!r}")
        for binding in option.lora_bindings:
            entry = lora_lib.get(binding.lora_id)
            if entry is None:
                fail(
                    f"step {step_id!r} option {option_id!r} cites unknown lora_id {binding.lora_id!r}"
                )
            strength_model = (
                entry.strength_model if binding.strength_model is None else binding.strength_model
            )
            strength_clip = (
                entry.strength_clip if binding.strength_clip is None else binding.strength_clip
            )
            source = [step_id, option_id]
            current = pending.get(binding.lora_id)
            if current is None:
                pending[binding.lora_id] = {
                    "lora_id": binding.lora_id,
                    "name": entry.name,
                    "strength_model": _round_strength(strength_model),
                    "strength_clip": _round_strength(strength_clip),
                    "sources": [source],
                }
                continue
            current["strength_model"] = _merge_strength(
                current["strength_model"], strength_model, policy
            )
            current["strength_clip"] = _merge_strength(
                current["strength_clip"], strength_clip, policy
            )
            current["sources"].append(source)


def _merge_strength(old: float, new: float, policy: str) -> float:
    # SPEC §4.2 step 4. max is the default. sum_clamp_1 caps at 1.0 only.
    if policy == "max":
        merged = max(old, new)
    elif policy == "sum_clamp_1":
        merged = min(1.0, old + new)
    elif policy == "last_wins":
        merged = new
    else:
        raise SchemaError(f"unknown strength_conflict {policy!r}")
    return _round_strength(merged)


def _round_strength(value: float) -> float:
    return round(float(value), 6)


def _public_pending(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "lora_id": item["lora_id"],
        "name": item["name"],
        "strength_model": item["strength_model"],
        "strength_clip": item["strength_clip"],
        "sources": item["sources"],
    }


def _apply_action(
    action: Action,
    step_id: str,
    step_enabled: dict[str, bool],
    theme: ThemeDefinition,
) -> None:
    if action.type == "enable_step":
        step_enabled[step_id] = True
        return
    if action.type == "disable_step":
        step_enabled[step_id] = False
        return
    if action.type == "rewrite_instructions":
        theme.instructions = action.instructions or ""
        return
    if action.type == "set_select_mode":
        theme.select_mode = action.select_mode or theme.select_mode
        return
    if action.type == "rewrite_options":
        _rewrite_options(theme, action)
        return
    raise SchemaError(f"unknown action type {action.type!r}")


def _rewrite_options(theme: ThemeDefinition, action: Action) -> None:
    # Order: remove, then keep, then add, then patch. keep is applied only when
    # the key was present, so an omitted keep does not clear the list, and an
    # explicit empty keep clears it.
    options = list(theme.options)
    if action.remove_option_ids is not None:
        remove = set(action.remove_option_ids)
        options = [option for option in options if option.option_id not in remove]
    if action.keep_option_ids is not None:
        keep = set(action.keep_option_ids)
        options = [option for option in options if option.option_id in keep]
    if action.add_options:
        existing = {option.option_id for option in options}
        for option in action.add_options:
            if option.option_id in existing:
                raise SchemaError(
                    f"add_options duplicates option_id {option.option_id!r} on theme {theme.theme_id!r}"
                )
            options.append(copy.deepcopy(option))
            existing.add(option.option_id)
    if action.patch_bindings:
        by_id = {option.option_id: option for option in options}
        for option_id, bindings in action.patch_bindings.items():
            target = by_id.get(option_id)
            if target is None:
                raise SchemaError(
                    f"patch_bindings option_id {option_id!r} is not in the runtime options "
                    f"of theme {theme.theme_id!r}"
                )
            target.lora_bindings = copy.deepcopy(bindings)
    theme.options = options


def _when_matches(when: WhenClause, answers: dict[str, dict[str, Any]]) -> bool:
    """Match `when` against a finished earlier step.

    Comparison ops (eq, neq, includes_*) require status ``ok``. A skipped step
    does not count as "not equal"; use ``op: skipped`` for that.
    """

    prior = answers.get(when.step_id)
    if prior is None:
        return False
    if when.op == "skipped":
        return prior.get("status") == "skipped"
    if when.op == "answered":
        return prior.get("status") == "ok"
    if prior.get("status") != "ok":
        return False
    selected = set(prior.get("selected") or [])
    wanted = when.option_ids
    if when.op == "eq":
        return selected == {wanted[0]}
    if when.op == "neq":
        return selected != {wanted[0]}
    if when.op == "includes_any":
        return bool(selected.intersection(wanted))
    if when.op == "includes_all":
        return set(wanted).issubset(selected)
    return False


def _report(
    *,
    answers: dict[str, Any],
    applied: list[dict[str, Any]],
    errors: list[str],
    notes: list[str],
    client: SystemOneClient,
    endpoint: str,
    model_name: str,
    key_source: str,
) -> dict[str, Any]:
    return {
        "answers": answers,
        "applied": applied,
        "errors": errors,
        "notes": notes,
        "stub": bool(getattr(client, "IS_STUB", False)),
        "api": {
            "endpoint": endpoint,
            "model": model_name,
            "stub": bool(getattr(client, "IS_STUB", False)),
            "key_source": key_source,
        },
    }


def _unit_float(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchemaError(f"{name} must be a number")
    number = float(value)
    if number < 0.0 or number > 1.0:
        raise SchemaError(f"{name} must be between 0 and 1")
    return number


__all__ = [
    "RunResult",
    "SequenceError",
    "dump_report",
    "run_sequence",
]
