"""Run one theme against SystemOne and append it to an upstream result.

Control flow:

- Theme Root and a downstream Theme both decide when this function runs.
  There is no ``run`` switch and no ``enable_json``. A downstream node is
  reached only when its caller hands over a real upstream result. Unselected
  option slots are ``ExecutionBlocker`` values produced by ``option_slot_values``,
  not a skip decision inside this function.
- Settings (endpoint, key, model, noul threshold, on_error, min confidence)
  come from a ``RouterSettings`` object.
- ``select_mode: single`` sends one ``choice`` question. One remaining option
  skips the call and selects that option. A default None option is added
  when the document has no none choice, so a single user option still asks
  SystemOne. Existing none-like options are reused and keep their slot index.
- ``select_mode: multi`` sends one ``noul`` question per option. A score at or
  above ``noul_threshold`` selects it. More than 32 options are split across
  requests that share the same state.
- An invalid choice fails. A choice whose ``confidence`` is below
  ``min_confidence`` is kept and marked ``low_confidence_kept``. There is no
  fallback option. The theme's ``none_option_id`` contributes no tags.
- A repeated ``theme_id`` raises ``SchemaError`` and does not call the API.
- Invalid theme JSON raises ``SchemaError`` and does not call the API.
- API and decision failures raise ``ThemeError`` when ``on_error`` is
  ``raise``. ``passthrough`` appends an error decision, keeps upstream tags,
  and does not raise. ``option_slot_values`` then emits that result on every
  option slot so a wired Aggregate still runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .schema.blocker import execution_blocker, is_execution_blocker
from .schema.types import (
    DecisionPayload,
    RouterSettings,
    SchemaError,
    ThemeDecision,
    ThemeDefinition,
    ThemeResult,
    build_settings,
    build_theme_result,
    empty_theme_result,
    parse_theme_for_run,
    public_decision,
)
from .systemone.client import (
    SystemOneClient,
    SystemOneError,
    resolve_api_key,
    resolve_model_name,
)

NOUL_BATCH = 32
NOUL_TRUE = "提示詞明確需要或強烈暗示此選項"
NOUL_FALSE = "提示詞不需要此選項"

_ROLES = {"root", "downstream"}


class ThemeError(RuntimeError):
    """The decision failed and ``on_error`` is ``raise``. ``result`` is safe to show."""

    def __init__(
        self,
        message: str,
        result: ThemeResult | None = None,
        report: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.result = result
        self.report = report


class _DecisionFailure(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


@dataclass
class ThemeOutcome:
    result: ThemeResult
    report: dict[str, Any] = field(default_factory=dict)


def dump_report(report: dict[str, Any]) -> str:
    """Compact JSON. Non-ASCII theme text stays readable."""

    return json.dumps(report, ensure_ascii=False, separators=(",", ":"))


def run_theme(
    *,
    theme_json: str | dict[str, Any],
    positive: str,
    negative: str = "",
    settings: RouterSettings,
    upstream: ThemeResult | DecisionPayload | None = None,
    role: str = "root",
    client: SystemOneClient | None = None,
) -> ThemeOutcome:
    """Decide this theme and return the accumulated result plus a report.

    ``SchemaError`` propagates for bad documents, a bad upstream object, a
    repeated theme id, and bad settings. Those paths do not call ``decide``.
    ``ThemeError`` propagates only when ``on_error`` is ``raise``.

    ``upstream`` may be a ``ThemeResult`` or a ``DecisionPayload``. The payload
    is unwrapped. Option-slot blocking is not done here.
    """

    if not isinstance(positive, str):
        raise SchemaError("positive must be a string")
    if negative is None:
        negative = ""
    if not isinstance(negative, str):
        raise SchemaError("negative must be a string")
    if role not in _ROLES:
        raise SchemaError("role must be root or downstream")
    if not isinstance(settings, RouterSettings):
        raise SchemaError("settings must be an S1_SETTINGS from SystemOne Settings")
    settings = build_settings(
        api_key=settings.api_key,
        api_model=settings.api_model,
        endpoint=settings.endpoint,
        noul_threshold=settings.noul_threshold,
        on_error=settings.on_error,
        min_confidence=settings.min_confidence,
    )
    on_error = settings.on_error
    threshold = settings.noul_threshold
    confidence_floor = settings.min_confidence
    endpoint = settings.endpoint
    if upstream is None:
        if role != "root":
            raise SchemaError("a downstream theme requires an S1_DECISION upstream")
        upstream_result = empty_theme_result()
    else:
        upstream_result = _unwrap_upstream(upstream)

    theme = parse_theme_for_run(theme_json)
    if upstream_result.get(theme.theme_id) is not None:
        raise SchemaError(
            f"theme_id {theme.theme_id!r} is already in the upstream result"
        )

    key, key_source = resolve_api_key(settings.api_key)
    model_name = resolve_model_name(settings.api_model)
    state = {"positive": positive, "negative": negative}
    notes: list[str] = []

    def finish(decision: ThemeDecision, *, called: bool) -> ThemeOutcome:
        errors = list(upstream_result.errors)
        if decision.error:
            errors.append(decision.error)
        result = build_theme_result(list(upstream_result.decisions) + [decision], errors)
        report = _report(
            theme=theme,
            decision=decision,
            result=result,
            notes=notes,
            called=called,
            endpoint=endpoint,
            model_name=model_name,
            key_source=key_source,
            client=client,
            role=role,
        )
        return ThemeOutcome(result=result, report=report)

    def fail(message: str, *, called: bool) -> ThemeOutcome:
        if on_error != "raise":
            notes.append("on_error=passthrough: this theme added no tags.")
        decision = ThemeDecision(
            theme_id=theme.theme_id,
            status="error",
            enabled=True,
            selected=[],
            tags=[],
            select_mode=theme.select_mode,
            error=message,
            reason="error",
        )
        outcome = finish(decision, called=called)
        if on_error == "raise":
            raise ThemeError(message, outcome.result, outcome.report)
        return outcome

    if client is None:
        client = SystemOneClient(api_key=key, endpoint=endpoint, model=model_name)
    if getattr(client, "IS_STUB", False):
        notes.append("SystemOne client is a stub; decide() did not send HTTP.")

    if not theme.options:
        return fail(f"theme {theme.theme_id!r} has no options", called=False)
    try:
        if theme.select_mode == "single":
            selected, raw = _run_single(client, state, theme, confidence_floor)
        elif theme.select_mode == "multi":
            selected, raw = _run_multi(client, state, theme, threshold)
        else:
            raise _DecisionFailure(
                f"theme {theme.theme_id!r} has select_mode {theme.select_mode!r}; "
                "expected single or multi"
            )
        tags, option_tags = _contribute(theme, selected)
        if raw.get("decision") == "low_confidence_kept":
            notes.append(
                f"theme {theme.theme_id!r} kept a low-confidence choice; there is no fallback option."
            )
        decision = ThemeDecision(
            theme_id=theme.theme_id,
            status="ok",
            enabled=True,
            selected=selected,
            tags=tags,
            select_mode=theme.select_mode,
            option_tags=option_tags,
            raw=raw,
            reason="ran",
        )
        http_called = not bool(raw.get("skipped_api"))
        return finish(decision, called=http_called)
    except _DecisionFailure as exc:
        return fail(str(exc), called=True)
    except SystemOneError as exc:
        return fail(f"SystemOne: {exc}", called=True)
    except ThemeError:
        raise
    except SchemaError:
        raise
    except Exception as exc:
        return fail(f"{type(exc).__name__}: {exc}", called=True)


def _unwrap_upstream(upstream: ThemeResult | DecisionPayload) -> ThemeResult:
    if isinstance(upstream, DecisionPayload):
        if not isinstance(upstream.result, ThemeResult):
            raise SchemaError("S1_DECISION is missing an accumulated result")
        return upstream.result
    if isinstance(upstream, ThemeResult):
        return upstream
    raise SchemaError(
        "upstream must be an S1_DECISION from a Theme option slot or Theme Collect"
    )


def option_slot_values(theme: ThemeDefinition, result: ThemeResult) -> list[Any]:
    """One value per option, in ``theme.options`` order.

    A selected option emits a ``DecisionPayload`` that carries the full
    accumulated result. Every selected slot of this theme shares that result,
    so a multi selection's tags are present on each selected socket.

    An error decision (``on_error=passthrough``) emits that same result on
    every option. Blocking every slot would also block Aggregate and drop
    upstream tags. ``none_option_id`` still contributes no tags; its slot
    emits when that option was selected.

    Any other option emits an ``ExecutionBlocker`` with message ``None``.
    """

    if not isinstance(theme, ThemeDefinition):
        raise SchemaError("option slots need a parsed theme")
    if not isinstance(result, ThemeResult):
        raise SchemaError("option slots need the theme result")
    decision = result.get(theme.theme_id)
    if decision is None:
        raise SchemaError(f"theme {theme.theme_id!r} has no decision to place on option slots")
    selected = set(decision.selected) if decision.status == "ok" else set()
    passthrough = decision.status == "error"
    slots: list[Any] = []
    for option in theme.options:
        if passthrough or option.option_id in selected:
            slots.append(
                DecisionPayload(
                    result=result,
                    slot_option_id=option.option_id,
                    theme_id=theme.theme_id,
                    emitted_reason="passthrough_error" if passthrough else "selected",
                )
            )
        else:
            slots.append(execution_blocker(None))
    return slots


def _run_single(client, state, theme: ThemeDefinition, min_confidence):
    if len(theme.options) == 1:
        only = theme.options[0].option_id
        return [only], {"skipped_api": True, "reason": "single_option", "choice": only}

    # Decision prompt is theme.instructions plus each option's description
    # keyed by option_id. Option tags and LoRA library tags are not sent;
    # they are applied after the answer in _contribute / Aggregate. If a
    # future prompt includes tags, send names only (strip :weight).
    qid = theme.theme_id
    questions = {
        qid: {
            "type": "choice",
            "instructions": theme.instructions,
            "criteria": {option.option_id: option.description for option in theme.options},
        }
    }
    response = _call(client, state, questions)
    raw_answer = response["answers"].get(qid)
    if not isinstance(raw_answer, dict) or "choice" not in raw_answer:
        raise _DecisionFailure(f"SystemOne choice response for theme {theme.theme_id!r} has no choice")
    choice = raw_answer.get("choice")
    valid = {option.option_id for option in theme.options}
    reason = None
    confidence = raw_answer.get("confidence")
    if choice not in valid:
        raise _DecisionFailure(
            f"theme {theme.theme_id!r} got choice {choice!r}, which is not an option"
        )
    if confidence is not None and _as_confidence(confidence, theme.theme_id) < min_confidence:
        reason = "low_confidence_kept"
    raw = {"stub": response.get("stub", False), "answers": {qid: raw_answer}}
    if reason:
        raw["decision"] = reason
    return [choice], raw


def _run_multi(client, state, theme: ThemeDefinition, threshold):
    # Noul prompt is theme.instructions plus option.label and
    # option.description. Option tags and library tags are not sent.
    questions = {}
    for option in theme.options:
        qid = f"{theme.theme_id}__{option.option_id}"
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
        response = _call(client, state, chunk)
        stub = stub and bool(response.get("stub", False))
        for qid in chunk:
            answer = response["answers"].get(qid)
            if not isinstance(answer, dict) or "noul" not in answer:
                raise _DecisionFailure(f"SystemOne noul response for {qid!r} has no noul")
            score = answer["noul"]
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                raise _DecisionFailure(f"SystemOne noul for {qid!r} is not a number")
            merged[qid] = {"noul": float(score)}
    selected = []
    for option in theme.options:
        qid = f"{theme.theme_id}__{option.option_id}"
        if merged[qid]["noul"] >= threshold:
            selected.append(option.option_id)
    return selected, {"stub": stub, "answers": merged}


def _call(client, state, questions) -> dict[str, Any]:
    try:
        response = client.decide(state, questions)
    except SystemOneError:
        raise
    except Exception as exc:
        raise _DecisionFailure(f"SystemOne: {type(exc).__name__}: {exc}") from exc
    if not isinstance(response, dict) or not isinstance(response.get("answers"), dict):
        raise _DecisionFailure("SystemOne response is missing an answers object")
    missing = [qid for qid in questions if qid not in response["answers"]]
    if missing:
        raise _DecisionFailure(f"SystemOne response is missing answers for {missing!r}")
    return response


def _as_confidence(value, theme_id: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _DecisionFailure(f"theme {theme_id!r} confidence is not a number")
    return float(value)


def _contribute(theme: ThemeDefinition, selected: list[str]):
    by_id = {option.option_id: option for option in theme.options}
    tags: list[str] = []
    seen: set[str] = set()
    option_tags: list[tuple[str, list[str]]] = []
    for option_id in selected:
        option = by_id.get(option_id)
        if option is None:
            raise _DecisionFailure(
                f"theme {theme.theme_id!r} selected unknown option {option_id!r}"
            )
        if theme.none_option_id is not None and option_id == theme.none_option_id:
            continue
        kept: list[str] = []
        for tag in option.tags:
            if tag not in kept:
                kept.append(tag)
            if tag not in seen:
                seen.add(tag)
                tags.append(tag)
        option_tags.append((option_id, kept))
    return tags, option_tags


def _report(
    *,
    theme: ThemeDefinition,
    decision: ThemeDecision,
    result: ThemeResult,
    notes: list[str],
    called: bool,
    endpoint: str,
    model_name: str,
    key_source: str,
    client: SystemOneClient | None,
    role: str,
) -> dict[str, Any]:
    return {
        "theme_id": theme.theme_id,
        "role": role,
        "status": decision.status,
        "enabled": decision.enabled,
        "selected": list(decision.selected),
        "tags": list(decision.tags),
        "decisions": [public_decision(item) for item in result.decisions],
        "accumulated_tags": list(result.tags),
        "errors": list(result.errors),
        "api": {
            "called": called,
            "endpoint": endpoint,
            "model": model_name,
            "key_source": key_source,
            "stub": bool(client is not None and getattr(client, "IS_STUB", False)),
        },
        "notes": list(notes),
    }


def _unit_float(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchemaError(f"{name} must be a number")
    number = float(value)
    if number < 0.0 or number > 1.0:
        raise SchemaError(f"{name} must be between 0 and 1")
    return number


__all__ = [
    "ThemeError",
    "ThemeOutcome",
    "dump_report",
    "is_execution_blocker",
    "option_slot_values",
    "run_theme",
]
