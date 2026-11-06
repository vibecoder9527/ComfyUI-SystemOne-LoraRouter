"""Load the custom node the way ComfyUI loads a folder, plus test doubles.

Importing this module does not open a socket.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "s1_lora_router"


def load_package():
    existing = sys.modules.get(PACKAGE_NAME)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(
        PACKAGE_NAME,
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE_NAME] = module
    spec.loader.exec_module(module)
    return module


PKG = load_package()
TYPES = importlib.import_module(PACKAGE_NAME + ".schema.types")
IDS = importlib.import_module(PACKAGE_NAME + ".schema.lora_ids")
THEME_IDS = importlib.import_module(PACKAGE_NAME + ".schema.theme_ids")
MIGRATE = importlib.import_module(PACKAGE_NAME + ".schema.migrate")
CLIENT = importlib.import_module(PACKAGE_NAME + ".systemone.client")
ENGINE = importlib.import_module(PACKAGE_NAME + ".theme_engine")
AGG = importlib.import_module(PACKAGE_NAME + ".aggregate")
APPLY = importlib.import_module(PACKAGE_NAME + ".apply_loras")


def read_example(name: str) -> str:
    return (ROOT / "examples" / name).read_text(encoding="utf-8")


def option(option_id, tags=None, label=None, description=None):
    item = {
        "option_id": option_id,
        "label": option_id if label is None else label,
        "description": option_id if description is None else description,
    }
    if tags is not None:
        item["tags"] = list(tags)
    return item


def theme_doc(theme_id="t", select_mode="single", options=None, **extra):
    document = {
        "version": 1,
        "theme_id": theme_id,
        "title": extra.pop("title", "T"),
        "instructions": extra.pop("instructions", "I"),
        "select_mode": select_mode,
        "options": [] if options is None else options,
    }
    document.update(extra)
    return document


def enable_doc(clauses=None, match="any"):
    return {"version": 1, "match": match, "clauses": [] if clauses is None else clauses}


def clause(theme_id, op, option_ids=None):
    item = {"theme_id": theme_id, "op": op}
    if option_ids is not None:
        item["option_ids"] = list(option_ids)
    return item


def lora_entries(*rows):
    entries = []
    for row in rows:
        item = {
            "lora_id": row["lora_id"],
            "name": row.get("name", row["lora_id"] + ".safetensors"),
            "strength_model": row.get("strength_model", 0.5),
            "strength_clip": row.get("strength_clip", 0.5),
        }
        if "tags" in row:
            item["tags"] = row["tags"]
        if "enabled_default" in row:
            item["enabled_default"] = row["enabled_default"]
        entries.append(item)
    return TYPES.parse_lora_library({"version": 1, "loras": entries})


class CountingClient(CLIENT.SystemOneClient):
    def __init__(self):
        super().__init__(api_key="k", endpoint=CLIENT.DEFAULT_ENDPOINT, model="m")
        self.calls = []

    def decide(self, state, questions):
        self.calls.append((state, questions))
        answers = {
            qid: CLIENT._canned_answer(qid, question)
            for qid, question in questions.items()
        }
        return {"stub": False, "answers": answers}


class FixedChoiceClient(CLIENT.SystemOneClient):
    def __init__(self, choice, confidence=1.0, include_confidence=True, noul=1.0):
        super().__init__(api_key="k", model="m")
        self.choice = choice
        self.confidence = confidence
        self.include_confidence = include_confidence
        self.noul = noul
        self.calls = []

    def decide(self, state, questions):
        self.calls.append((state, questions))
        answers = {}
        for qid, question in questions.items():
            if question["type"] == "choice":
                item = {"choice": self.choice, "probabilities": {}}
                if self.include_confidence:
                    item["confidence"] = self.confidence
                answers[qid] = item
            else:
                answers[qid] = {"noul": self.noul}
        return {"stub": True, "answers": answers}


class ScoreClient(CLIENT.SystemOneClient):
    """Noul scores keyed by option id. Choice answers use `choice`."""

    def __init__(self, scores=None, choice="anime", confidence=1.0):
        super().__init__(api_key="k", model="m")
        self.scores = {} if scores is None else scores
        self.choice = choice
        self.confidence = confidence
        self.calls = []

    def decide(self, state, questions):
        self.calls.append((state, questions))
        answers = {}
        for qid, question in questions.items():
            if question["type"] == "choice":
                answers[qid] = {"choice": self.choice, "confidence": self.confidence}
            else:
                option_id = qid.split("__", 1)[1]
                answers[qid] = {"noul": self.scores.get(option_id, 0.0)}
        return {"stub": True, "answers": answers}


class FakeHTTPResponse:
    def __init__(self, body, status=200, headers=None):
        if isinstance(body, (bytes, bytearray)):
            raw = bytes(body)
        elif isinstance(body, str):
            raw = body.encode("utf-8")
        else:
            raw = json.dumps(body).encode("utf-8")
        self._body = raw
        self.status = status
        self.headers = headers or {}

    def read(self):
        return self._body

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def payload_from_request(req):
    return json.loads(req.data.decode("utf-8"))


def canned_urlopen(req, timeout=None):
    body = payload_from_request(req)
    return FakeHTTPResponse(
        {
            "model": body.get("model"),
            "answers": {
                qid: CLIENT._canned_answer(qid, question)
                for qid, question in body["questions"].items()
            },
            "usage": {"input_tokens": 12, "output_tokens": 0},
        }
    )


def run_theme(**kwargs):
    params = {
        "theme_json": theme_doc(options=[option("a", ["tag"])]),
        "positive": "p",
        "negative": "",
        "run": "enabled",
        "enable_json": enable_doc(),
        "api_key": "k",
    }
    params.update(kwargs)
    if "client" not in params:
        params["client"] = CountingClient()
    return ENGINE.run_theme(**params)
