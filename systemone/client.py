"""SystemOne HTTP client stub.

SPEC §8 contract this stub builds but does not send:

- POST ``https://system-one.dev/v1/systemone``
- ``Authorization: Bearer <key>`` when a key is available
- ``Idempotency-Key: <uuid4>``
- Body: ``model``, ``state`` (``{positive, negative}``), ``questions`` (1–32)
- Question types used here: ``choice`` (single) and ``noul`` (multi)

STUB: `decide` does not open a socket. It returns a canned decision so a graph
can run offline.

Canned policy (deterministic):

- ``choice`` selects the first criteria key and reports confidence 1.0
- ``noul`` returns 1.0, so the default threshold 0.5 selects that option

The API key comes from the node widget, otherwise the ``SYSTEM_ONE_API_KEY``
environment variable (SPEC §6). The widget wins when it is non-empty.
``api_model`` is not hard-coded to a live model id; an empty widget becomes
``unspecified`` until the user sets one (SPEC §6 open item).
"""

from __future__ import annotations

import os
import uuid
from typing import Any

DEFAULT_ENDPOINT = "https://system-one.dev/v1/systemone"
ENV_API_KEY = "SYSTEM_ONE_API_KEY"
# Not a production model id. SPEC §6 leaves the real default open.
SKELETON_MODEL_FALLBACK = "unspecified"
MAX_QUESTIONS = 32

STUB_DECISION_NOTE = (
    "STUB: SystemOne client did not send HTTP. "
    "single uses type choice and picks the first option; "
    "multi uses type noul and returns 1.0 "
    "(selected when noul >= noul_threshold)."
)


class SystemOneError(RuntimeError):
    """The request broke the SystemOne contract, or a live call failed.

    The skeleton raises this only for local contract problems (question count,
    missing choice criteria, unknown type). It does not contact the network.
    """


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
    """Offline stand-in for POST /v1/systemone.

    ``IS_STUB`` stays true until a live transport replaces `decide`.
    """

    IS_STUB = True

    def __init__(
        self,
        api_key: str = "",
        endpoint: str = DEFAULT_ENDPOINT,
        model: str = "",
    ) -> None:
        self.api_key = api_key or ""
        self.endpoint = (endpoint or "").strip() or DEFAULT_ENDPOINT
        self.model = resolve_model_name(model)

    def build_headers(self, idempotency_key: str) -> dict[str, str]:
        """Headers a live POST would send. The stub does not transmit them."""

        headers = {
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
        """Return canned answers for `questions`. Does not perform I/O.

        The returned object includes the body that a live client would POST,
        plus ``has_authorization`` (never the key). Callers that put this
        object into a user-visible report should copy ``answers`` only.
        """

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

        idempotency_key = str(uuid.uuid4())
        body = self.build_body(state, questions)
        # Built so a live transport can replace the next line with an HTTP POST
        # of `body` to `self.endpoint` using `build_headers(idempotency_key)`.
        _headers = self.build_headers(idempotency_key)
        answers = {
            qid: _canned_answer(qid, question) for qid, question in questions.items()
        }
        return {
            "stub": True,
            "answers": answers,
            "idempotency_key": idempotency_key,
            "endpoint": self.endpoint,
            "request": body,
            "has_authorization": "Authorization" in _headers,
        }


def _canned_answer(qid: str, question: dict[str, Any]) -> dict[str, Any]:
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
