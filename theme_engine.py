"""Run one Theme node against SystemOne and append it to an upstream result.

Control flow:

- ``run=disabled`` (the default) does not call SystemOne and contributes no tags.
- ``run=enabled`` always decides. This is the explicit root switch.
- ``run=when_upstream`` decides only when ``enable_json`` matches the upstream
  result. Empty clauses match nothing. A missing upstream does not match.
  Option ops (``eq``, ``neq``, ``includes_any``, ``includes_all``) require the
  named theme's status to be ``ok``. ``skipped`` and ``answered`` read status.
  A theme id that is absent from the upstream result makes that clause false.
- ``match`` is ``any`` (OR, the default) or ``all`` (AND).
- ``select_mode: single`` sends one ``choice`` question. One remaining option
  skips the call and selects that option. This runner does not invent ``__none__``.
- ``select_mode: multi`` sends one ``noul`` question per option. A score at or
  above ``noul_threshold`` selects it. More than 32 options are split across
  requests that share the same state.
- An invalid choice fails. A choice whose ``confidence`` is below
  ``min_confidence`` is kept and marked ``low_confidence_kept``. There is no
  fallback option. The theme's ``none_option_id`` contributes no tags.
- Disabled and unmatched themes append a ``skipped`` decision so a later
  ``op: skipped`` can target them. Nested chains only see decisions already
  in the upstream result.
- A repeated ``theme_id`` raises ``SchemaError`` and does not call the API.
- Invalid theme or enable JSON raises ``SchemaError`` and does not call the API.
- API and decision failures raise ``ThemeError`` when ``on_error`` is
  ``raise``. ``passthrough`` appends an error decision, keeps upstream tags,
  and does not raise.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .schema.types import (
    EnableClause,
    EnableRules,
    SchemaError,
    ThemeDecision,
    ThemeDefinition,
    ThemeResult,
    build_theme_result,
    empty_theme_result,
    parse_enable_rules,
    parse_theme,
    public_decision,
)
from .systemone.client import (
    DEFAULT_ENDPOINT,
    SystemOneClient,
    SystemOneError,
    resolve_api_key,
    resolve_model_name,
)

NOUL_BATCH = 32
NOUL_TRUE = "提示詞明確需要或強烈暗示此選項"
NOUL_FALSE = "提示詞不需要此選項"

_ON_ERROR = {"passthrough", "raise"}
_RUN = {"disabled", "enabled", "when_upstream"}


class ThemeError(RuntimeError):
    """The theme was enabled and ``on_error`` is ``raise``. `result` is safe to show."""

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
    run: str = "disabled",
    enable_json: str | dict[str, Any] | None = None,
    upstream: ThemeResult | None = None,
    api_key: str = "",
    api_model: str = "",
    endpoint: str = DEFAULT_ENDPOINT,
    noul_threshold: float = 0.5,
    on_error: str = "passthrough",
    min_confidence: float = 0.0,
    client: SystemOneClient | None = None,
) -> ThemeOutcome:
    """Decide this theme and return the accumulated result plus a report.

    ``SchemaError`` propagates for bad documents, a bad upstream object, a
    repeated theme id, and bad widget values. Those paths do not call
    ``decide``. ``ThemeError`` propagates only when ``on_error`` is ``raise``.
    """

    if not isinstance(positive, str):
        raise SchemaError("positive must be a string")
    if not isinstance(negative, str):
        raise SchemaError("negative must be a string")
    if on_error not in _ON_ERROR:
        raise SchemaError(f"on_error must be one of: {', '.join(sorted(_ON_ERROR))}")
    if run not in _RUN:
        raise SchemaError(f"run must be one of: {', '.join(sorted(_RUN))}")
    threshold = _unit_float("noul_threshold", noul_threshold)
    confidence_floor = _unit_float("min_confidence", min_confidence)
    endpoint = (endpoint or "").strip() or DEFAULT_ENDPOINT
    if not (endpoint.startswith("https://") or endpoint.startswith("http://")):
        raise SchemaError("endpoint must start with http:// or https://")
    if upstream is None:
        upstream = empty_theme_result()
    elif not isinstance(upstream, ThemeResult):
        raise SchemaError("upstream must be an S1_THEME_RESULT from a Theme or Theme Collect node")

    theme = parse_theme(theme_json)
    rules = parse_enable_rules(enable_json if enable_json is not None else {"clauses": []})
    if upstream.get(theme.theme_id) is not None:
        raise SchemaError(
            f"theme_id {theme.theme_id!r} is already in the upstream result"
        )

    key, key_source = resolve_api_key(api_key)
    model_name = resolve_model_name(api_model)
    state = {"positive": positive, "negative": negative}
    notes: list[str] = []

    def finish(decision: ThemeDecision, *, called: bool) -> ThemeOutcome:
        errors = list(upstream.errors)
        if decision.error:
            errors.append(decision.error)
        result = build_theme_result(list(upstream.decisions) + [decision], errors)
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
            run=run,
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

    active, skip_reason = _activation(run, rules, upstream)
    if not active:
        if skip_reason == "disabled":
            notes.append("run=disabled: SystemOne was not called and this theme added no tags.")
        else:
            notes.append(
                "enable rules did not match the upstream result; "
                "SystemOne was not called and this theme added no tags."
            )
        decision = ThemeDecision(
            theme_id=theme.theme_id,
            status="skipped",
            enabled=False,
            selected=[],
            tags=[],
            select_mode=theme.select_mode,
            reason=skip_reason,
        )
        return finish(decision, called=False)

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


def rules_match(rules: EnableRules, upstream: ThemeResult) -> bool:
    """Return whether `rules` enable a theme. Empty clauses match nothing."""

    if not rules.clauses:
        return False
    results = [_clause_matches(clause, upstream) for clause in rules.clauses]
    if rules.match == "all":
        return all(results)
    return any(results)


def _activation(run: str, rules: EnableRules, upstream: ThemeResult) -> tuple[bool, str]:
    if run == "disabled":
        return False, "disabled"
    if run == "enabled":
        return True, "enabled"
    if rules_match(rules, upstream):
        return True, "when_upstream"
    return False, "enable_rules_unmatched"


def _clause_matches(clause: EnableClause, upstream: ThemeResult) -> bool:
    decision = upstream.get(clause.theme_id)
    if decision is None:
        return False
    if clause.op == "skipped":
        return decision.status == "skipped"
    if clause.op == "answered":
        return decision.status == "ok"
    if decision.status != "ok":
        return False
    selected = set(decision.selected)
    wanted = clause.option_ids
    if clause.op == "eq":
        return selected == {wanted[0]}
    if clause.op == "neq":
        return selected != {wanted[0]}
    if clause.op == "includes_any":
        return bool(selected.intersection(wanted))
    if clause.op == "includes_all":
        return set(wanted).issubset(selected)
    return False


def _run_single(client, state, theme: ThemeDefinition, min_confidence):
    if len(theme.options) == 1:
        only = theme.options[0].option_id
        return [only], {"skipped_api": True, "reason": "single_option", "choice": only}

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
    run: str,
) -> dict[str, Any]:
    return {
        "theme_id": theme.theme_id,
        "run": run,
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
    "rules_match",
    "run_theme",
]
