"""SystemOne HTTP client.

SPEC §8 contract:

- POST ``https://system-one.dev/v1/systemone``
- ``Authorization: Bearer <key>`` (required for a live call)
- ``Idempotency-Key: <uuid4>``
- Body: ``model``, ``state`` (``{positive, negative}``), ``questions`` (1–32)
- Question types used here: ``choice`` (single) and ``noul`` (multi)
- Choice reply: ``answers[qid].choice`` plus ``probabilities`` / ``confidence``
- Noul reply: ``answers[qid].noul`` ∈ [0, 1]

The API key comes from the node widget, otherwise the ``SYSTEM_ONE_API_KEY``
environment variable (SPEC §6). The widget wins when it is non-empty.
``api_model`` is not hard-coded to a live model id; an empty widget becomes
``unspecified`` until the user sets one (SPEC §6 open item).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from typing import Any

DEFAULT_ENDPOINT = "https://system-one.dev/v1/systemone"
DEFAULT_TIMEOUT = 60.0
ENV_API_KEY = "SYSTEM_ONE_API_KEY"
# Not a production model id. SPEC §6 leaves the real default open.
SKELETON_MODEL_FALLBACK = "unspecified"
MAX_QUESTIONS = 32


class SystemOneError(RuntimeError):
    """The request broke the SystemOne contract, or a live call failed."""


def resolve_api_key(widget_value: str | None) -> tuple[str, str]:
    """Return ``(key, source)`` where source is ``widget``, ``env``, or ``missing``.

    The key itself must not be written into reports or logs.
    """

    widget = (widget_value or "").strip()
    if widget:
        return widget, "widget"
    env = os.environ.get(ENV_API_KEY, "").strip()
    if env:
        return env, "env"
    return "", "missing"


def resolve_model_name(api_model: str | None) -> str:
    name = (api_model or "").strip()
    return name or SKELETON_MODEL_FALLBACK


class SystemOneClient:
    """POST /v1/systemone via the standard library.

    ``IS_STUB`` is false. ``decide`` opens a socket. Tests mock
    ``urllib.request.urlopen`` (or override ``decide``) so unittest never
    needs a live key.
    """

    IS_STUB = False

    def __init__(
        self,
        api_key: str = "",
        endpoint: str = DEFAULT_ENDPOINT,
        model: str = "",
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.api_key = api_key or ""
        self.endpoint = (endpoint or "").strip() or DEFAULT_ENDPOINT
        self.model = resolve_model_name(model)
        self.timeout = DEFAULT_TIMEOUT if timeout is None else float(timeout)

    def build_headers(self, idempotency_key: str) -> dict[str, str]:
        """Headers sent with the live POST. Never log the bearer token."""

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def build_body(
        self,
        state: dict[str, Any],
        questions: dict[str, Any],
    ) -> dict[str, Any]:
        """Request body from SPEC §4.2. ``state`` is an object, not a bare string."""

        return {
            "model": self.model,
            "state": {
                "positive": "" if state.get("positive") is None else str(state.get("positive")),
                "negative": "" if state.get("negative") is None else str(state.get("negative")),
            },
            "questions": questions,
        }

    def decide(self, state: dict[str, Any], questions: dict[str, Any]) -> dict[str, Any]:
        """POST `questions` and return the parsed SystemOne answers.

        Raises ``SystemOneError`` for contract problems, a missing API key,
        HTTP errors, timeouts, invalid JSON, or a response without ``answers``.
        The returned object includes ``has_authorization`` (never the key).
        Callers that put this object into a user-visible report should copy
        ``answers`` only.
        """

        _validate_request(state, questions)
        if not self.api_key:
            raise SystemOneError(
                "api_key is required to call SystemOne "
                "(set the api_key widget or SYSTEM_ONE_API_KEY)"
            )

        idempotency_key = str(uuid.uuid4())
        body = self.build_body(state, questions)
        headers = self.build_headers(idempotency_key)
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                http_status = getattr(response, "status", None) or response.getcode()
        except urllib.error.HTTPError as exc:
            try:
                message = _http_error_message(exc)
            finally:
                try:
                    exc.close()
                except Exception:
                    pass
            raise SystemOneError(message) from exc
        except TimeoutError as exc:
            raise SystemOneError(
                f"SystemOne request timed out after {self.timeout}s"
            ) from exc
        except urllib.error.URLError as exc:
            raise SystemOneError(_url_error_message(exc, self.timeout)) from exc
        except OSError as exc:
            raise SystemOneError(f"SystemOne request failed: {exc}") from exc

        try:
            parsed = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SystemOneError("SystemOne response is not valid JSON") from exc

        answers = _require_answers(questions, parsed)
        result: dict[str, Any] = {
            "stub": False,
            "answers": answers,
            "idempotency_key": idempotency_key,
            "endpoint": self.endpoint,
            "request": body,
            "has_authorization": "Authorization" in headers,
            "http_status": http_status,
        }
        if isinstance(parsed, dict) and "model" in parsed:
            result["model"] = parsed["model"]
        if isinstance(parsed, dict) and "usage" in parsed:
            result["usage"] = parsed["usage"]
        return result


def _validate_request(state: Any, questions: Any) -> None:
    if not isinstance(state, dict):
        raise SystemOneError("state must be an object")
    if not isinstance(questions, dict) or not questions:
        raise SystemOneError("questions must contain 1–32 items")
    if len(questions) > MAX_QUESTIONS:
        raise SystemOneError(
            f"questions has {len(questions)} items; the SystemOne limit is {MAX_QUESTIONS}"
        )
    for qid, question in questions.items():
        if not isinstance(qid, str) or not qid:
            raise SystemOneError("question ids must be non-empty strings")
        if not isinstance(question, dict) or "type" not in question:
            raise SystemOneError(f"question {qid!r} is missing type")
        qtype = question.get("type")
        if qtype == "choice":
            criteria = question.get("criteria")
            if not isinstance(criteria, dict) or not criteria:
                raise SystemOneError(f"choice question {qid!r} has no criteria")
        elif qtype == "noul":
            continue
        else:
            raise SystemOneError(
                f"question {qid!r} has unsupported type {qtype!r}; "
                "this package sends choice and noul only"
            )


def _require_answers(questions: dict[str, Any], payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SystemOneError("SystemOne response is not a JSON object")
    answers = payload.get("answers")
    if not isinstance(answers, dict):
        raise SystemOneError("SystemOne response is missing an answers object")
    missing = [qid for qid in questions if qid not in answers]
    if missing:
        raise SystemOneError(f"SystemOne response is missing answers for {missing!r}")
    for qid, question in questions.items():
        answer = answers[qid]
        if not isinstance(answer, dict):
            raise SystemOneError(f"SystemOne answer for {qid!r} is not an object")
        qtype = question.get("type")
        if qtype == "choice" and "choice" not in answer:
            raise SystemOneError(f"SystemOne choice response for {qid!r} has no choice")
        if qtype == "noul" and "noul" not in answer:
            raise SystemOneError(f"SystemOne noul response for {qid!r} has no noul")
    return answers


def _http_error_message(exc: urllib.error.HTTPError) -> str:
    status = getattr(exc, "code", None)
    error_code = None
    detail = ""
    headers = getattr(exc, "headers", None) or getattr(exc, "hdrs", None)
    try:
        if headers is not None:
            error_code = headers.get("X-System-One-Error-Code")
    except Exception:
        error_code = None
    try:
        raw = exc.read()
        if raw:
            detail = raw.decode("utf-8", errors="replace").strip()
            if len(detail) > 300:
                detail = detail[:300] + "…"
    except Exception:
        detail = ""
    message = f"SystemOne HTTP {status}"
    if error_code:
        message += f" X-System-One-Error-Code={error_code}"
    if detail:
        message += f": {detail}"
    return message


def _url_error_message(exc: urllib.error.URLError, timeout: float) -> str:
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
        return f"SystemOne request timed out after {timeout}s: {reason}"
    return f"SystemOne request failed: {reason}"


def _canned_answer(qid: str, question: dict[str, Any]) -> dict[str, Any]:
    """Deterministic answers for unittest clients that override ``decide``.

    Live ``SystemOneClient.decide`` does not call this. Choice picks the first
    criteria key at confidence 1.0; noul returns 1.0.
    """

    qtype = question.get("type")
    if qtype == "choice":
        criteria = question.get("criteria")
        if not isinstance(criteria, dict) or not criteria:
            raise SystemOneError(f"choice question {qid!r} has no criteria")
        first = next(iter(criteria))
        probabilities = {key: (1.0 if key == first else 0.0) for key in criteria}
        return {"choice": first, "probabilities": probabilities, "confidence": 1.0}
    if qtype == "noul":
        return {"noul": 1.0}
    raise SystemOneError(
        f"question {qid!r} has unsupported type {qtype!r}; this package sends choice and noul only"
    )
