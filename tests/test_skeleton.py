"""Tests: schema, live HTTP client (mocked), dependency walk, node registration.

Run from the repo root: python -m unittest tests.test_skeleton
Unittest never opens a live SystemOne socket and never needs a real API key.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import io
import json
import os
import shutil
import subprocess
import sys
import unittest
import urllib.error
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "s1_lora_router_skeleton"


def load_package():
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
CLIENT = importlib.import_module(PACKAGE_NAME + ".systemone.client")
ENGINE = importlib.import_module(PACKAGE_NAME + ".sequence_engine")
APPLY = importlib.import_module(PACKAGE_NAME + ".apply_loras")


def _read(name: str) -> str:
    return (ROOT / "examples" / name).read_text(encoding="utf-8")


def _lora(entries):
    return TYPES.parse_lora_library({"version": 1, "loras": entries})


def _theme(themes):
    return TYPES.parse_theme_library({"version": 1, "themes": themes})


def _option(option_id, bindings=None, label=None, description="desc"):
    return {
        "option_id": option_id,
        "label": label or option_id,
        "description": description,
        "lora_bindings": bindings or [],
    }


def _binding(lora_id, strength_model=None, strength_clip=None):
    item = {"lora_id": lora_id}
    if strength_model is not None:
        item["strength_model"] = strength_model
    if strength_clip is not None:
        item["strength_clip"] = strength_clip
    return item


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


def _payload_from_request(req):
    return json.loads(req.data.decode("utf-8"))


def _canned_http_body(req):
    body = _payload_from_request(req)
    return {
        "model": body.get("model"),
        "answers": {
            qid: CLIENT._canned_answer(qid, question)
            for qid, question in body["questions"].items()
        },
        "usage": {"input_tokens": 12, "output_tokens": 0},
    }


def _canned_urlopen(req, timeout=None):
    return FakeHTTPResponse(_canned_http_body(req))


class FixedChoiceClient(CLIENT.SystemOneClient):
    def __init__(self, choice, confidence=1.0, include_confidence=True):
        super().__init__(api_key="k", model="m")
        self.choice = choice
        self.confidence = confidence
        self.include_confidence = include_confidence
        self.calls = []

    def decide(self, state, questions):
        self.calls.append(questions)
        answers = {}
        for qid, question in questions.items():
            if question["type"] == "choice":
                item = {"choice": self.choice, "probabilities": {}}
                if self.include_confidence:
                    item["confidence"] = self.confidence
                answers[qid] = item
            else:
                answers[qid] = {"noul": 1.0}
        return {"stub": True, "answers": answers}


class SchemaTests(unittest.TestCase):
    def test_empty_defaults_and_example_files(self):
        self.assertEqual(_read("lora_library.empty.json").strip(), TYPES.EMPTY_LORA_LIBRARY_JSON)
        self.assertEqual(_read("theme_library.empty.json").strip(), TYPES.EMPTY_THEME_LIBRARY_JSON)
        self.assertEqual(_read("sequence.empty.json").strip(), TYPES.EMPTY_SEQUENCE_JSON)
        loras = TYPES.parse_lora_library(TYPES.EMPTY_LORA_LIBRARY_JSON)
        themes = TYPES.parse_theme_library(TYPES.EMPTY_THEME_LIBRARY_JSON)
        sequence = TYPES.parse_sequence(TYPES.EMPTY_SEQUENCE_JSON)
        self.assertEqual(loras.version, 1)
        self.assertEqual(loras.loras, {})
        self.assertEqual(themes.themes, {})
        self.assertEqual(sequence.steps, [])
        minimal_loras = TYPES.parse_lora_library(_read("lora_library.minimal.json"))
        minimal_themes = TYPES.parse_theme_library(_read("theme_library.minimal.json"))
        minimal_sequence = TYPES.parse_sequence(_read("sequence.minimal.json"))
        TYPES.validate_refs(minimal_sequence, minimal_themes, minimal_loras)
        self.assertEqual(set(minimal_loras.loras), {"style_anime_v3", "style_realistic", "char_a"})
        self.assertEqual(minimal_themes.get("art_style").select_mode, "single")
        self.assertEqual(minimal_themes.get("character_pack").select_mode, "multi")
        self.assertIsNone(minimal_themes.get("art_style").none_option_id)
        self.assertFalse(hasattr(minimal_themes.get("art_style"), "fallback_option_id"))
        minimal_theme_doc = json.loads(_read("theme_library.minimal.json"))
        for theme in minimal_theme_doc["themes"]:
            self.assertNotIn("fallback_option_id", theme)
        self.assertEqual(
            [option.option_id for option in minimal_themes.get("art_style").options],
            ["anime", "realistic"],
        )

    def test_rejects_bad_documents(self):
        with self.assertRaises(TYPES.SchemaError) as ctx:
            TYPES.parse_lora_library("{")
        self.assertIn("not valid JSON", str(ctx.exception))
        with self.assertRaises(TYPES.SchemaError):
            TYPES.parse_lora_library({"loras": [{"lora_id": "a", "name": "a.safetensors", "strength_model": 1, "strength_clip": 1}, {"lora_id": "a", "name": "b.safetensors", "strength_model": 1, "strength_clip": 1}]})
        with self.assertRaises(TYPES.SchemaError):
            TYPES.parse_lora_library({"version": 2, "loras": []})
        with self.assertRaises(TYPES.SchemaError):
            TYPES.parse_lora_library({"loras": [], "extra": 1})
        with self.assertRaises(TYPES.SchemaError):
            TYPES.parse_theme_library(
                {
                    "themes": [
                        {
                            "theme_id": "t",
                            "title": "t",
                            "instructions": "i",
                            "select_mode": "single",
                            "options": [_option("has space")],
                        }
                    ]
                }
            )
        with self.assertRaises(TYPES.SchemaError):
            TYPES.parse_sequence(
                {
                    "steps": [
                        {"step_id": "s1", "theme_id": "t", "dependencies": []},
                        {
                            "step_id": "s2",
                            "theme_id": "t",
                            "dependencies": [
                                {"when": {"step_id": "s1", "op": "eq", "option_ids": ["a", "b"]}, "actions": []}
                            ],
                        },
                    ]
                }
            )
        with self.assertRaises(TYPES.SchemaError):
            TYPES.parse_sequence(
                {
                    "steps": [
                        {
                            "step_id": "s1",
                            "theme_id": "t",
                            "dependencies": [
                                {"when": {"step_id": "s0", "op": "skipped", "option_ids": ["x"]}, "actions": []}
                            ],
                        }
                    ]
                }
            )

    def test_refs_require_known_ids_and_earlier_steps(self):
        loras = _lora(
            [{"lora_id": "known", "name": "known.safetensors", "strength_model": 1, "strength_clip": 1}]
        )
        themes = _theme(
            [
                {
                    "theme_id": "t",
                    "title": "T",
                    "instructions": "I",
                    "select_mode": "single",
                    "options": [_option("a", [_binding("missing")])],
                }
            ]
        )
        sequence = TYPES.parse_sequence(
            {"steps": [{"step_id": "s1", "theme_id": "t", "dependencies": []}]}
        )
        with self.assertRaises(TYPES.SchemaError) as ctx:
            TYPES.validate_refs(sequence, themes, loras)
        self.assertIn("missing", str(ctx.exception))
        themes_ok = _theme(
            [
                {
                    "theme_id": "t",
                    "title": "T",
                    "instructions": "I",
                    "select_mode": "single",
                    "options": [_option("a", [_binding("known")])],
                }
            ]
        )
        later = TYPES.parse_sequence(
            {
                "steps": [
                    {
                        "step_id": "s1",
                        "theme_id": "t",
                        "dependencies": [
                            {
                                "when": {"step_id": "s2", "op": "answered"},
                                "actions": [{"type": "disable_step"}],
                            }
                        ],
                    },
                    {"step_id": "s2", "theme_id": "t", "dependencies": []},
                ]
            }
        )
        with self.assertRaises(TYPES.SchemaError) as ctx:
            TYPES.validate_refs(later, themes_ok, loras)
        self.assertIn("earlier step", str(ctx.exception))


class LoraIdHelperTests(unittest.TestCase):
    def test_next_lora_id_uses_smallest_free_positive_integer(self):
        self.assertEqual(IDS.next_lora_id([]), "lora_1")
        self.assertEqual(IDS.next_lora_id(["lora_1", "lora_2"]), "lora_3")
        self.assertEqual(IDS.next_lora_id(["lora_1", "lora_3"]), "lora_2")
        self.assertEqual(IDS.next_lora_id(["style_anime_v3", "char_a"]), "lora_1")
        self.assertEqual(IDS.next_lora_id(["lora_2", "style_anime_v3"]), "lora_1")
        self.assertEqual(IDS.next_lora_id(["lora_0", "lora_01", "Lora_1"]), "lora_1")
        self.assertEqual(IDS.next_lora_id(["", "lora_1", None, "lora_4"]), "lora_2")

    def test_ensure_lora_ids_keeps_manual_ids_and_fills_gaps(self):
        original = [
            {"lora_id": "", "name": "new.safetensors", "strength_model": 0.2, "strength_clip": 0.9},
            {"lora_id": "style_anime_v3", "name": "a.safetensors", "strength_model": 0.8, "strength_clip": 0.4},
            {"lora_id": "lora_1", "name": "b.safetensors", "strength_model": 0.5, "strength_clip": 0.5},
            {"name": "missing.safetensors"},
            {"lora_id": "   ", "name": "blank.safetensors"},
        ]
        filled = IDS.ensure_lora_ids(original)
        self.assertEqual(
            [entry["lora_id"] for entry in filled],
            ["lora_2", "style_anime_v3", "lora_1", "lora_3", "lora_4"],
        )
        self.assertEqual(filled[1]["strength_clip"], 0.4)
        self.assertEqual(original[0]["lora_id"], "")
        self.assertIsNot(filled[0], original[0])
        self.assertNotIn("lora_id", original[3])

        minimal = json.loads(_read("lora_library.minimal.json"))
        ensured = IDS.ensure_lora_ids(minimal["loras"])
        self.assertEqual(
            [entry["lora_id"] for entry in ensured],
            ["style_anime_v3", "style_realistic", "char_a"],
        )
        parsed = TYPES.parse_lora_library(_read("lora_library.minimal.json"))
        self.assertEqual(set(parsed.loras), {"style_anime_v3", "style_realistic", "char_a"})
        self.assertEqual(parsed.get("style_anime_v3").strength_model, 0.8)
        self.assertEqual(parsed.get("style_anime_v3").strength_clip, 0.8)

    def test_shared_strength_writes_both_fields_and_drops_strength_key(self):
        fields = IDS.shared_strength_fields(0.8)
        self.assertEqual(fields, {"strength_model": 0.8, "strength_clip": 0.8})
        self.assertEqual(IDS.shared_strength_fields(1), {"strength_model": 1, "strength_clip": 1})
        out = IDS.apply_shared_strength(
            {
                "lora_id": "style_anime_v3",
                "name": "a.safetensors",
                "strength_model": 0.2,
                "strength_clip": 0.9,
                "strength": 1,
            },
            0.8,
        )
        self.assertEqual(out["lora_id"], "style_anime_v3")
        self.assertEqual(out["strength_model"], 0.8)
        self.assertEqual(out["strength_clip"], 0.8)
        self.assertNotIn("strength", out)
        self.assertEqual(
            TYPES.parse_lora_library(
                {"version": 1, "loras": [{"lora_id": "a", "name": "a.safetensors", **fields}]}
            )
            .get("a")
            .strength_clip,
            0.8,
        )
        with self.assertRaises(TypeError):
            IDS.shared_strength_fields(True)
        with self.assertRaises(TypeError):
            IDS.shared_strength_fields("0.8")
        with self.assertRaises(ValueError):
            IDS.shared_strength_fields(float("inf"))

    def test_parse_still_requires_id_and_both_strengths(self):
        with self.assertRaises(TYPES.SchemaError):
            TYPES.parse_lora_library(
                {"loras": [{"name": "a.safetensors", "strength_model": 1, "strength_clip": 1}]}
            )
        with self.assertRaises(TYPES.SchemaError):
            TYPES.parse_lora_library(
                {"loras": [{"lora_id": "a", "name": "a.safetensors", "strength_model": 1}]}
            )
        library = TYPES.parse_lora_library(
            {
                "loras": [
                    {
                        "lora_id": "style_anime_v3",
                        "name": "a.safetensors",
                        "strength_model": 0.85,
                        "strength_clip": 0.8,
                    }
                ]
            }
        )
        entry = library.get("style_anime_v3")
        self.assertEqual(entry.strength_model, 0.85)
        self.assertEqual(entry.strength_clip, 0.8)


class ThemeIdHelperTests(unittest.TestCase):
    def test_next_theme_id_and_next_option_id_fill_gaps(self):
        self.assertEqual(THEME_IDS.next_theme_id([]), "theme_1")
        self.assertEqual(THEME_IDS.next_theme_id(["theme_1", "theme_2"]), "theme_3")
        self.assertEqual(THEME_IDS.next_theme_id(["theme_1", "theme_3"]), "theme_2")
        self.assertEqual(THEME_IDS.next_theme_id(["art_style", "character_pack"]), "theme_1")
        self.assertEqual(THEME_IDS.next_theme_id(["theme_2", "art_style"]), "theme_1")
        self.assertEqual(THEME_IDS.next_theme_id(["theme_0", "theme_01", "Theme_1"]), "theme_1")
        self.assertEqual(THEME_IDS.next_theme_id(["", "theme_1", None, "theme_4"]), "theme_2")
        self.assertEqual(THEME_IDS.next_option_id([]), "option_1")
        self.assertEqual(THEME_IDS.next_option_id(["option_1", "option_3"]), "option_2")
        self.assertEqual(THEME_IDS.next_option_id(["anime", "option_2"]), "option_1")
        self.assertEqual(THEME_IDS.next_option_id(["option_0", "Option_1"]), "option_1")

    def test_ensure_theme_ids_keeps_manual_ids_and_scopes_options(self):
        original = [
            {
                "theme_id": "",
                "title": "New",
                "options": [
                    {"option_id": "anime", "label": "a"},
                    {"option_id": ""},
                    {"option_id": "option_1", "label": "kept"},
                ],
            },
            {
                "theme_id": "theme_1",
                "options": [{"option_id": "   "}, {"option_id": "waifu_a"}],
            },
            {"theme_id": "art_style", "title": "Style"},
            {"title": "Missing"},
            {"theme_id": "   ", "options": []},
        ]
        filled = THEME_IDS.ensure_theme_ids(original)
        self.assertEqual(
            [theme["theme_id"] for theme in filled],
            ["theme_2", "theme_1", "art_style", "theme_3", "theme_4"],
        )
        self.assertEqual(
            [option["option_id"] for option in filled[0]["options"]],
            ["anime", "option_2", "option_1"],
        )
        self.assertEqual(
            [option["option_id"] for option in filled[1]["options"]],
            ["option_1", "waifu_a"],
        )
        self.assertNotIn("options", filled[2])
        self.assertEqual(filled[0]["title"], "New")
        self.assertEqual(original[0]["theme_id"], "")
        self.assertEqual(original[0]["options"][1]["option_id"], "")
        self.assertIsNot(filled[0], original[0])
        self.assertIsNot(filled[0]["options"][0], original[0]["options"][0])
        self.assertNotIn("theme_id", original[3])

        minimal = json.loads(_read("theme_library.minimal.json"))
        ensured = THEME_IDS.ensure_theme_ids(minimal["themes"])
        self.assertEqual(
            [theme["theme_id"] for theme in ensured],
            ["art_style", "character_pack"],
        )
        self.assertEqual(
            [option["option_id"] for option in ensured[0]["options"]],
            ["anime", "realistic"],
        )

    def test_ensure_option_ids_does_not_see_other_lists(self):
        first = THEME_IDS.ensure_option_ids([{"option_id": ""}, {"option_id": "anime"}])
        second = THEME_IDS.ensure_option_ids([{"option_id": ""}, {"option_id": "anime"}])
        self.assertEqual([item["option_id"] for item in first], ["option_1", "anime"])
        self.assertEqual([item["option_id"] for item in second], ["option_1", "anime"])
        with self.assertRaises(TypeError):
            THEME_IDS.ensure_theme_ids({"theme_id": "t"})
        with self.assertRaises(TypeError):
            THEME_IDS.ensure_option_ids({"option_id": "o"})

    def test_fallback_option_id_is_rejected_and_none_remains(self):
        with self.assertRaises(TYPES.SchemaError) as ctx:
            TYPES.parse_theme_library(
                {
                    "themes": [
                        {
                            "theme_id": "t",
                            "title": "T",
                            "instructions": "I",
                            "select_mode": "single",
                            "fallback_option_id": "a",
                            "options": [_option("a")],
                        }
                    ]
                }
            )
        self.assertIn("unknown field", str(ctx.exception))
        self.assertIn("fallback_option_id", str(ctx.exception))
        kept = _theme(
            [
                {
                    "theme_id": "art_style",
                    "title": "Style",
                    "instructions": "Pick one.",
                    "select_mode": "single",
                    "none_option_id": "none",
                    "options": [_option("none"), _option("anime")],
                }
            ]
        )
        self.assertEqual(kept.get("art_style").none_option_id, "none")
        self.assertEqual(
            [option.option_id for option in kept.get("art_style").options],
            ["none", "anime"],
        )
        with self.assertRaises(TYPES.SchemaError) as ctx:
            _theme(
                [
                    {
                        "theme_id": "t",
                        "title": "T",
                        "instructions": "I",
                        "select_mode": "single",
                        "none_option_id": "missing",
                        "options": [_option("a")],
                    }
                ]
            )
        self.assertIn("none_option_id", str(ctx.exception))
        result = ENGINE.run_sequence(
            model=object(),
            clip=None,
            lora_lib=_lora([]),
            theme_lib=kept,
            sequence_json={"steps": [{"step_id": "s1", "theme_id": "art_style"}]},
            positive="",
            client=FixedChoiceClient("none"),
        )
        self.assertEqual(result.report["answers"]["s1"]["selected"], ["none"])

    def test_parse_still_requires_theme_and_option_ids(self):
        with self.assertRaises(TYPES.SchemaError):
            TYPES.parse_theme_library(
                {
                    "themes": [
                        {
                            "title": "T",
                            "instructions": "I",
                            "select_mode": "single",
                            "options": [],
                        }
                    ]
                }
            )
        with self.assertRaises(TYPES.SchemaError):
            TYPES.parse_theme_library(
                {
                    "themes": [
                        {
                            "theme_id": "t",
                            "title": "T",
                            "instructions": "I",
                            "select_mode": "single",
                            "options": [{"label": "L", "description": "D"}],
                        }
                    ]
                }
            )


class ClientTests(unittest.TestCase):
    def test_key_resolution_prefers_widget(self):
        previous = os.environ.get(CLIENT.ENV_API_KEY)
        try:
            os.environ[CLIENT.ENV_API_KEY] = "from-env"
            self.assertEqual(CLIENT.resolve_api_key(" from-widget "), ("from-widget", "widget"))
            self.assertEqual(CLIENT.resolve_api_key("   "), ("from-env", "env"))
            self.assertEqual(CLIENT.resolve_api_key(""), ("from-env", "env"))
            os.environ.pop(CLIENT.ENV_API_KEY, None)
            self.assertEqual(CLIENT.resolve_api_key(""), ("", "missing"))
        finally:
            if previous is None:
                os.environ.pop(CLIENT.ENV_API_KEY, None)
            else:
                os.environ[CLIENT.ENV_API_KEY] = previous
        self.assertEqual(CLIENT.resolve_model_name("  "), CLIENT.SKELETON_MODEL_FALLBACK)
        self.assertEqual(CLIENT.resolve_model_name("live-model"), "live-model")

    def test_decide_posts_json_and_parses_choice_and_noul(self):
        secret = "sekret-token-xyz"
        client = CLIENT.SystemOneClient(api_key=secret, model="")
        self.assertFalse(client.IS_STUB)
        questions = {
            "s1": {"type": "choice", "criteria": {"anime": "a", "real": "b"}},
            "s2__a": {"type": "noul"},
        }
        seen = {}

        def urlopen(req, timeout=None):
            seen["req"] = req
            seen["timeout"] = timeout
            body = _payload_from_request(req)
            self.assertEqual(body["model"], CLIENT.SKELETON_MODEL_FALLBACK)
            self.assertEqual(body["state"], {"positive": "p", "negative": ""})
            self.assertEqual(set(body["questions"]), {"s1", "s2__a"})
            return FakeHTTPResponse(
                {
                    "model": "live-model-echo",
                    "answers": {
                        "s1": {
                            "type": "choice",
                            "choice": "anime",
                            "probabilities": {"anime": 0.9, "real": 0.1},
                            "confidence": 0.8,
                            "extra": "kept",
                        },
                        "s2__a": {"type": "noul", "noul": 0.7},
                    },
                    "usage": {"input_tokens": 9, "output_tokens": 0},
                }
            )

        with mock.patch("urllib.request.urlopen", side_effect=urlopen):
            result = client.decide({"positive": "p", "negative": ""}, questions)
        req = seen["req"]
        self.assertEqual(seen["timeout"], CLIENT.DEFAULT_TIMEOUT)
        self.assertEqual(req.get_full_url(), CLIENT.DEFAULT_ENDPOINT)
        sent_headers = {key.lower(): value for key, value in req.header_items()}
        self.assertEqual(sent_headers["authorization"], f"Bearer {secret}")
        uuid.UUID(sent_headers["idempotency-key"])
        self.assertEqual(sent_headers["content-type"], "application/json")
        self.assertFalse(result["stub"])
        self.assertTrue(result["has_authorization"])
        self.assertEqual(result["http_status"], 200)
        self.assertEqual(result["answers"]["s1"]["choice"], "anime")
        self.assertEqual(result["answers"]["s1"]["confidence"], 0.8)
        self.assertEqual(result["answers"]["s1"]["probabilities"]["anime"], 0.9)
        self.assertEqual(result["answers"]["s1"]["extra"], "kept")
        self.assertEqual(result["answers"]["s2__a"]["noul"], 0.7)
        self.assertEqual(result["request"]["model"], CLIENT.SKELETON_MODEL_FALLBACK)
        self.assertEqual(result["request"]["state"], {"positive": "p", "negative": ""})
        self.assertEqual(result["model"], "live-model-echo")
        self.assertEqual(result["usage"]["input_tokens"], 9)
        uuid.UUID(result["idempotency_key"])
        self.assertEqual(result["idempotency_key"], sent_headers["idempotency-key"])
        dumped = json.dumps(result)
        self.assertNotIn(secret, dumped)
        headers = client.build_headers(result["idempotency_key"])
        self.assertEqual(headers["Authorization"], f"Bearer {secret}")
        self.assertEqual(headers["Idempotency-Key"], result["idempotency_key"])

    def test_decide_requires_api_key_before_socket(self):
        client = CLIENT.SystemOneClient(api_key="", model="named")
        with mock.patch("urllib.request.urlopen") as urlopen:
            with self.assertRaises(CLIENT.SystemOneError) as ctx:
                client.decide({"positive": "", "negative": ""}, {"q": {"type": "noul"}})
        urlopen.assert_not_called()
        self.assertIn("api_key", str(ctx.exception))

    def test_decide_http_error_timeout_and_bad_json(self):
        client = CLIENT.SystemOneClient(api_key="k", model="m", timeout=5)
        questions = {"q": {"type": "noul"}}
        state = {"positive": "p", "negative": ""}

        def http_error(req, timeout=None):
            headers = {"X-System-One-Error-Code": "unauthorized"}
            raise urllib.error.HTTPError(
                req.get_full_url(),
                401,
                "Unauthorized",
                headers,
                io.BytesIO(b'{"error":"nope"}'),
            )

        with mock.patch("urllib.request.urlopen", side_effect=http_error):
            with self.assertRaises(CLIENT.SystemOneError) as ctx:
                client.decide(state, questions)
        self.assertIn("401", str(ctx.exception))
        self.assertIn("unauthorized", str(ctx.exception))

        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaises(CLIENT.SystemOneError) as ctx:
                client.decide(state, questions)
        self.assertIn("timed out", str(ctx.exception).lower())
        self.assertIn("5", str(ctx.exception))

        with mock.patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError(TimeoutError("timed out")),
        ):
            with self.assertRaises(CLIENT.SystemOneError) as ctx:
                client.decide(state, questions)
        self.assertIn("timed out", str(ctx.exception).lower())

        with mock.patch("urllib.request.urlopen", return_value=FakeHTTPResponse("not-json")):
            with self.assertRaises(CLIENT.SystemOneError) as ctx:
                client.decide(state, questions)
        self.assertIn("JSON", str(ctx.exception))

        with mock.patch(
            "urllib.request.urlopen",
            return_value=FakeHTTPResponse({"model": "m"}),
        ):
            with self.assertRaises(CLIENT.SystemOneError) as ctx:
                client.decide(state, questions)
        self.assertIn("answers", str(ctx.exception))

        with mock.patch(
            "urllib.request.urlopen",
            return_value=FakeHTTPResponse({"answers": {"other": {"noul": 1.0}}}),
        ):
            with self.assertRaises(CLIENT.SystemOneError) as ctx:
                client.decide(state, questions)
        self.assertIn("missing answers", str(ctx.exception))

    def test_decide_rejects_contract_errors_without_http(self):
        secret = "sekret-token-xyz"
        client = CLIENT.SystemOneClient(api_key=secret, model="")
        with mock.patch("urllib.request.urlopen") as urlopen:
            with self.assertRaises(CLIENT.SystemOneError):
                client.decide({"positive": "", "negative": ""}, {})
            too_many = {f"q{i}": {"type": "noul"} for i in range(33)}
            with self.assertRaises(CLIENT.SystemOneError):
                client.decide({"positive": "p", "negative": ""}, too_many)
            with self.assertRaises(CLIENT.SystemOneError):
                client.decide({"positive": "p", "negative": ""}, {"q": {"type": "score"}})
            with self.assertRaises(CLIENT.SystemOneError):
                client.decide(
                    {"positive": "p", "negative": ""},
                    {"s1": {"type": "choice", "criteria": {}}},
                )
        urlopen.assert_not_called()


class EngineTests(unittest.TestCase):
    def test_minimal_example_picks_anime_then_character(self):
        loras = TYPES.parse_lora_library(_read("lora_library.minimal.json"))
        themes = TYPES.parse_theme_library(_read("theme_library.minimal.json"))
        before = [option.option_id for option in themes.get("character_pack").options]
        client = CountingClient()
        model = object()
        clip = object()
        result = ENGINE.run_sequence(
            model=model,
            clip=clip,
            lora_lib=loras,
            theme_lib=themes,
            sequence_json=_read("sequence.minimal.json"),
            positive="anime girl",
            negative="",
            api_key="sekret-token-xyz",
            api_model="",
            client=client,
        )
        self.assertIs(result.model, model)
        self.assertIs(result.clip, clip)
        self.assertEqual(result.report["answers"]["s1"]["selected"], ["anime"])
        self.assertEqual(result.report["answers"]["s2"]["selected"], ["waifu_a"])
        self.assertEqual(
            [item["lora_id"] for item in result.report["applied"]],
            ["char_a", "style_anime_v3"],
        )
        by_id = {item["lora_id"]: item for item in result.report["applied"]}
        self.assertEqual(by_id["style_anime_v3"]["strength_model"], 0.85)
        self.assertEqual(by_id["style_anime_v3"]["strength_clip"], 0.8)
        self.assertEqual(by_id["style_anime_v3"]["sources"], [["s1", "anime"]])
        self.assertFalse(by_id["style_anime_v3"]["loaded"])
        self.assertEqual(by_id["char_a"]["strength_model"], 0.9)
        self.assertEqual(by_id["char_a"]["sources"], [["s2", "waifu_a"]])
        self.assertEqual(result.report["errors"], [])
        self.assertEqual(result.report["api"]["model"], "unspecified")
        self.assertEqual(result.report["api"]["key_source"], "widget")
        self.assertNotIn("sekret-token-xyz", ENGINE.dump_report(result.report))
        self.assertFalse(result.report["stub"])
        notes = " ".join(result.report["notes"])
        self.assertIn("did not patch weights", notes)
        self.assertIn("ComfyUI APIs unavailable", notes)
        self.assertEqual(len(client.calls), 2)
        _state, first = client.calls[0]
        self.assertEqual(first["s1"]["type"], "choice")
        self.assertEqual(_state, {"positive": "anime girl", "negative": ""})
        _state, second = client.calls[1]
        self.assertEqual(list(second), ["s2__waifu_a"])
        self.assertEqual(second["s2__waifu_a"]["type"], "noul")
        self.assertTrue(second["s2__waifu_a"]["instructions"].startswith("在動漫畫風下"))
        self.assertEqual(before, ["waifu_a", "waifu_b"])
        self.assertEqual(
            [option.option_id for option in themes.get("character_pack").options],
            before,
        )

    def test_realistic_choice_leaves_character_step_skipped(self):
        loras = TYPES.parse_lora_library(_read("lora_library.minimal.json"))
        themes = TYPES.parse_theme_library(_read("theme_library.minimal.json"))
        result = ENGINE.run_sequence(
            model=object(),
            clip=None,
            lora_lib=loras,
            theme_lib=themes,
            sequence_json=_read("sequence.minimal.json"),
            positive="photo",
            client=FixedChoiceClient("realistic"),
        )
        self.assertEqual(result.report["answers"]["s1"]["selected"], ["realistic"])
        self.assertEqual(result.report["answers"]["s2"]["status"], "skipped")
        self.assertEqual(
            [item["lora_id"] for item in result.report["applied"]],
            ["style_realistic"],
        )
        self.assertEqual(result.report["applied"][0]["strength_model"], 0.7)
        self.assertEqual(result.report["applied"][0]["strength_clip"], 0.7)

    def test_strength_conflict_policies(self):
        loras = _lora(
            [{"lora_id": "L", "name": "L.safetensors", "strength_model": 0.1, "strength_clip": 0.1}]
        )
        themes = _theme(
            [
                {
                    "theme_id": "t",
                    "title": "T",
                    "instructions": "I",
                    "select_mode": "multi",
                    "options": [
                        _option("a", [_binding("L", 0.4, 0.9)]),
                        _option("b", [_binding("L", 0.8, 0.2)]),
                    ],
                }
            ]
        )
        sequence = {"steps": [{"step_id": "s", "theme_id": "t", "dependencies": []}]}
        for policy, model_strength, clip_strength in (
            ("max", 0.8, 0.9),
            ("sum_clamp_1", 1.0, 1.0),
            ("last_wins", 0.8, 0.2),
        ):
            result = ENGINE.run_sequence(
                model=object(),
                clip=None,
                lora_lib=loras,
                theme_lib=themes,
                sequence_json=sequence,
                positive="",
                strength_conflict=policy,
                client=CountingClient(),
            )
            applied = result.report["applied"]
            self.assertEqual(len(applied), 1, policy)
            self.assertEqual(applied[0]["strength_model"], model_strength, policy)
            self.assertEqual(applied[0]["strength_clip"], clip_strength, policy)
            self.assertEqual(applied[0]["sources"], [["s", "a"], ["s", "b"]])

    def test_single_option_skips_api_and_batches_noul(self):
        loras = _lora([])
        single = _theme(
            [
                {
                    "theme_id": "t",
                    "title": "T",
                    "instructions": "I",
                    "select_mode": "single",
                    "options": [_option("only")],
                }
            ]
        )
        client = CountingClient()
        result = ENGINE.run_sequence(
            model=object(),
            clip=None,
            lora_lib=loras,
            theme_lib=single,
            sequence_json={"steps": [{"step_id": "s", "theme_id": "t"}]},
            positive="",
            client=client,
        )
        self.assertEqual(client.calls, [])
        self.assertEqual(result.report["answers"]["s"]["selected"], ["only"])
        self.assertTrue(result.report["answers"]["s"]["raw"]["skipped_api"])

        options = [_option(f"opt{i}") for i in range(33)]
        multi = _theme(
            [
                {
                    "theme_id": "t",
                    "title": "T",
                    "instructions": "I",
                    "select_mode": "multi",
                    "options": options,
                }
            ]
        )
        client = CountingClient()
        result = ENGINE.run_sequence(
            model=object(),
            clip=None,
            lora_lib=loras,
            theme_lib=multi,
            sequence_json={"steps": [{"step_id": "s", "theme_id": "t"}]},
            positive="p",
            negative="n",
            client=client,
        )
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(len(client.calls[0][1]), 32)
        self.assertEqual(len(client.calls[1][1]), 1)
        self.assertEqual(len(result.report["answers"]["s"]["selected"]), 33)

    def test_low_confidence_keeps_choice_and_invalid_choice_fails(self):
        loras = _lora(
            [{"lora_id": "R", "name": "R.safetensors", "strength_model": 0.2, "strength_clip": 0.2}]
        )
        themes = _theme(
            [
                {
                    "theme_id": "style",
                    "title": "S",
                    "instructions": "I",
                    "select_mode": "single",
                    "options": [
                        _option("anime"),
                        _option("realistic", [_binding("R")]),
                    ],
                }
            ]
        )
        sequence = {"steps": [{"step_id": "s1", "theme_id": "style"}]}
        low = ENGINE.run_sequence(
            model=object(),
            clip=None,
            lora_lib=loras,
            theme_lib=themes,
            sequence_json=sequence,
            positive="",
            min_confidence=0.5,
            client=FixedChoiceClient("anime", confidence=0.1),
        )
        self.assertEqual(low.report["answers"]["s1"]["selected"], ["anime"])
        self.assertEqual(low.report["answers"]["s1"]["raw"]["decision"], "low_confidence_kept")
        self.assertEqual(low.report["applied"], [])
        boundary = ENGINE.run_sequence(
            model=object(),
            clip=None,
            lora_lib=loras,
            theme_lib=themes,
            sequence_json=sequence,
            positive="",
            min_confidence=0.5,
            client=FixedChoiceClient("anime", confidence=0.5),
        )
        self.assertEqual(boundary.report["answers"]["s1"]["selected"], ["anime"])
        self.assertNotIn("decision", boundary.report["answers"]["s1"]["raw"])
        missing_confidence = ENGINE.run_sequence(
            model=object(),
            clip=None,
            lora_lib=loras,
            theme_lib=themes,
            sequence_json=sequence,
            positive="",
            min_confidence=0.9,
            client=FixedChoiceClient("anime", include_confidence=False),
        )
        self.assertEqual(missing_confidence.report["answers"]["s1"]["selected"], ["anime"])
        self.assertNotIn("decision", missing_confidence.report["answers"]["s1"]["raw"])
        with self.assertRaises(ENGINE.SequenceError) as ctx:
            ENGINE.run_sequence(
                model=object(),
                clip=None,
                lora_lib=loras,
                theme_lib=themes,
                sequence_json=sequence,
                positive="",
                client=FixedChoiceClient("nope"),
            )
        self.assertIn("nope", str(ctx.exception))
        self.assertIn("s1", str(ctx.exception))
        self.assertEqual(ctx.exception.report["applied"], [])

        # Last matching dependency wins. neq does not treat a skip as a mismatch.
        gate = _theme(
            [
                {
                    "theme_id": "gate",
                    "title": "G",
                    "instructions": "I",
                    "select_mode": "single",
                    "options": [_option("yes")],
                },
                {
                    "theme_id": "next",
                    "title": "N",
                    "instructions": "I",
                    "select_mode": "single",
                    "options": [_option("go")],
                },
            ]
        )
        disabled = ENGINE.run_sequence(
            model=object(),
            clip=None,
            lora_lib=_lora([]),
            theme_lib=gate,
            sequence_json={
                "steps": [
                    {"step_id": "s1", "theme_id": "gate", "enabled_by_default": False},
                    {
                        "step_id": "s2",
                        "theme_id": "next",
                        "enabled_by_default": False,
                        "dependencies": [
                            {
                                "when": {"step_id": "s1", "op": "neq", "option_ids": ["yes"]},
                                "actions": [{"type": "enable_step"}],
                            }
                        ],
                    },
                ]
            },
            positive="",
        )
        self.assertEqual(disabled.report["answers"]["s1"]["status"], "skipped")
        self.assertEqual(disabled.report["answers"]["s2"]["status"], "skipped")
        enabled_by_skip = ENGINE.run_sequence(
            model=object(),
            clip=None,
            lora_lib=_lora([]),
            theme_lib=gate,
            sequence_json={
                "steps": [
                    {"step_id": "s1", "theme_id": "gate", "enabled_by_default": False},
                    {
                        "step_id": "s2",
                        "theme_id": "next",
                        "enabled_by_default": False,
                        "dependencies": [
                            {
                                "when": {"step_id": "s1", "op": "skipped"},
                                "actions": [{"type": "enable_step"}],
                            }
                        ],
                    },
                ]
            },
            positive="",
        )
        self.assertEqual(enabled_by_skip.report["answers"]["s2"]["selected"], ["go"])
        last_wins = ENGINE.run_sequence(
            model=object(),
            clip=None,
            lora_lib=_lora([]),
            theme_lib=gate,
            sequence_json={
                "steps": [
                    {"step_id": "s1", "theme_id": "gate"},
                    {
                        "step_id": "s2",
                        "theme_id": "next",
                        "enabled_by_default": True,
                        "dependencies": [
                            {
                                "when": {"step_id": "s1", "op": "answered"},
                                "actions": [{"type": "disable_step"}],
                            },
                            {
                                "when": {"step_id": "s1", "op": "eq", "option_ids": ["yes"]},
                                "actions": [{"type": "enable_step"}],
                            },
                        ],
                    },
                ]
            },
            positive="",
        )
        self.assertEqual(last_wins.report["answers"]["s2"]["status"], "ok")

    def test_missing_file_follows_on_error_when_comfy_api_is_present(self):
        loras = _lora(
            [{"lora_id": "L", "name": "missing.safetensors", "strength_model": 0.4, "strength_clip": 0.4}]
        )
        themes = _theme(
            [
                {
                    "theme_id": "t",
                    "title": "T",
                    "instructions": "I",
                    "select_mode": "single",
                    "options": [_option("only", [_binding("L")])],
                }
            ]
        )
        sequence = {"steps": [{"step_id": "s", "theme_id": "t"}]}

        def missing_api():
            def get_full_path(_kind, _name):
                return None

            def load_torch_file(_path, safe_load=True):
                raise AssertionError("missing file must not be loaded")

            def load_lora_for_models(*_args):
                raise AssertionError("missing file must not be patched")

            return (load_lora_for_models, load_torch_file, get_full_path), None

        original = APPLY._import_comfy
        APPLY._import_comfy = missing_api
        try:
            model = object()
            result = ENGINE.run_sequence(
                model=model,
                clip=None,
                lora_lib=loras,
                theme_lib=themes,
                sequence_json=sequence,
                positive="",
                on_error="passthrough",
            )
            self.assertIs(result.model, model)
            self.assertFalse(result.report["applied"][0]["loaded"])
            self.assertIn("missing.safetensors", result.report["errors"][0])
            with self.assertRaises(APPLY.ApplyError):
                ENGINE.run_sequence(
                    model=model,
                    clip=None,
                    lora_lib=loras,
                    theme_lib=themes,
                    sequence_json=sequence,
                    positive="",
                    on_error="raise",
                )
        finally:
            APPLY._import_comfy = original

    def test_comfy_hook_patches_when_the_file_resolves(self):
        loras = _lora(
            [{"lora_id": "L", "name": "found.safetensors", "strength_model": 0.3, "strength_clip": 0.6}]
        )
        themes = _theme(
            [
                {
                    "theme_id": "t",
                    "title": "T",
                    "instructions": "I",
                    "select_mode": "single",
                    "options": [_option("only", [_binding("L", 0.3, 0.6)])],
                }
            ]
        )
        new_model = object()
        seen = {}

        def present_api():
            def get_full_path(_kind, name):
                return f"/loras/{name}"

            def load_torch_file(path, safe_load=True):
                seen["path"] = path
                seen["safe_load"] = safe_load
                return {"path": path}

            dummy_clip = object()

            def load_lora_for_models(model, clip, lora_object, strength_model, strength_clip):
                seen["call"] = (model, clip, lora_object, strength_model, strength_clip)
                return (new_model, dummy_clip)

            return (load_lora_for_models, load_torch_file, get_full_path), None

        original = APPLY._import_comfy
        APPLY._import_comfy = present_api
        model = object()
        try:
            result = ENGINE.run_sequence(
                model=model,
                clip=None,
                lora_lib=loras,
                theme_lib=themes,
                sequence_json={"steps": [{"step_id": "s", "theme_id": "t"}]},
                positive="",
            )
        finally:
            APPLY._import_comfy = original
        self.assertIs(result.model, new_model)
        self.assertIsNone(result.clip)
        self.assertTrue(result.report["applied"][0]["loaded"])
        self.assertEqual(seen["path"], "/loras/found.safetensors")
        self.assertTrue(seen["safe_load"])
        self.assertIs(seen["call"][0], model)
        self.assertIsNone(seen["call"][1])
        self.assertEqual(seen["call"][3], 0.3)
        self.assertEqual(seen["call"][4], 0.6)

    def test_dump_report_keeps_non_ascii(self):
        text = ENGINE.dump_report({"answers": {}, "label": "畫風"})
        self.assertIn("畫風", text)
        self.assertNotIn("\\u", text)
        self.assertIn('"answers":{', text)


class NodeTests(unittest.TestCase):
    def test_registration_and_input_contract(self):
        mappings = PKG.NODE_CLASS_MAPPINGS
        self.assertEqual(
            set(mappings),
            {"S1LoraLibrary", "S1ThemeLibrary", "S1ThemeSequence"},
        )
        self.assertIs(mappings["S1LoraLibrary"], PKG.NODE_CLASS_MAPPINGS["S1LoraLibrary"])
        for name, node in mappings.items():
            self.assertEqual(node.CATEGORY, "SystemOne/LoraRouter")
            self.assertTrue(callable(node.INPUT_TYPES))
        self.assertEqual(mappings["S1LoraLibrary"].FUNCTION, "build")
        self.assertEqual(mappings["S1ThemeLibrary"].FUNCTION, "build")
        self.assertEqual(mappings["S1ThemeSequence"].FUNCTION, "apply")
        self.assertEqual(mappings["S1LoraLibrary"].RETURN_TYPES, ("S1_LORA_LIB",))
        self.assertEqual(mappings["S1ThemeLibrary"].RETURN_TYPES, ("S1_THEME_LIB",))
        self.assertEqual(mappings["S1ThemeSequence"].RETURN_TYPES, ("MODEL", "CLIP", "STRING"))
        self.assertEqual(
            mappings["S1ThemeSequence"].RETURN_NAMES,
            ("model", "clip", "report_json"),
        )
        sequence_inputs = mappings["S1ThemeSequence"].INPUT_TYPES()
        required_names = list(sequence_inputs["required"])
        self.assertEqual(
            required_names,
            [
                "model",
                "theme_lib",
                "lora_lib",
                "positive",
                "negative",
                "sequence_json",
                "api_key",
                "api_model",
            ],
        )
        self.assertEqual(required_names[required_names.index("positive") + 1], "negative")
        negative_spec = sequence_inputs["required"]["negative"]
        self.assertEqual(negative_spec[0], "STRING")
        self.assertTrue(negative_spec[1]["multiline"])
        self.assertEqual(negative_spec[1]["default"], "")
        self.assertEqual(
            set(sequence_inputs["optional"]),
            {
                "clip",
                "endpoint",
                "noul_threshold",
                "on_error",
                "strength_conflict",
                "min_confidence",
            },
        )
        self.assertNotIn("negative", sequence_inputs["optional"])
        apply_params = list(inspect.signature(mappings["S1ThemeSequence"].apply).parameters)
        self.assertEqual(apply_params[apply_params.index("positive") + 1], "negative")
        self.assertEqual(
            inspect.signature(mappings["S1ThemeSequence"].apply).parameters["negative"].default,
            "",
        )
        self.assertTrue(sequence_inputs["required"]["theme_lib"][1]["forceInput"])
        self.assertTrue(sequence_inputs["required"]["lora_lib"][1]["forceInput"])
        self.assertFalse(sequence_inputs["required"]["sequence_json"][1]["dynamicPrompts"])
        self.assertEqual(
            sequence_inputs["optional"]["endpoint"][1]["default"],
            "https://system-one.dev/v1/systemone",
        )
        self.assertEqual(sequence_inputs["optional"]["on_error"][1]["default"], "passthrough")
        self.assertEqual(sequence_inputs["optional"]["strength_conflict"][1]["default"], "max")
        self.assertEqual(
            mappings["S1LoraLibrary"].INPUT_TYPES()["required"]["library_json"][1]["default"],
            '{ "loras": [] }',
        )
        self.assertEqual(
            PKG.NODE_DISPLAY_NAME_MAPPINGS["S1ThemeSequence"],
            "Theme Sequence",
        )
        self.assertEqual(PKG.WEB_DIRECTORY, "./js")
        self.assertEqual(
            list(PKG.__all__),
            ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"],
        )
        for node in mappings.values():
            self.assertIn("visual editor", node.DESCRIPTION)
        scripts = sorted(path.name for path in (ROOT / "js").glob("*.js"))
        self.assertEqual(scripts, ["s1_editors.js", "s1_model.js"])
        extension = (ROOT / "js" / "s1_editors.js").read_text(encoding="utf-8")
        self.assertIn('name: "SystemOne.LoraRouter.UI"', extension)
        self.assertIn("registerSidebarTab", extension)
        self.assertIn("Open visual editor", extension)

    def test_lora_picker_reads_object_info_and_keeps_typed_names(self):
        self.assertEqual(PKG.WEB_DIRECTORY, "./js")
        self.assertTrue((ROOT / "js" / "s1_editors.js").is_file())
        self.assertTrue((ROOT / "js" / "s1_model.js").is_file())
        editors = (ROOT / "js" / "s1_editors.js").read_text(encoding="utf-8")
        model_js = (ROOT / "js" / "s1_model.js").read_text(encoding="utf-8")
        self.assertIn('from "../../scripts/api.js"', editors)
        self.assertIn("/object_info/LoraLoader", editors)
        self.assertIn("/object_info/LoraLoaderModelOnly", editors)
        self.assertIn('"/object_info"', editors)
        self.assertIn("loraNamesFromInfo", editors)
        self.assertIn("lora_name", model_js)
        self.assertIn("/models/loras", editors)
        self.assertIn("Browse loras", editors)
        self.assertIn("Needs a running ComfyUI.", editors)
        self.assertIn("Typed names still work.", editors)
        self.assertIn("`${entryPath}.name`", editors)
        self.assertNotIn("S1_THEME_SEQ", editors)
        init_text = (ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn('WEB_DIRECTORY = "./js"', init_text)
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        for name in ("s1_editors.js", "s1_model.js"):
            checked = subprocess.run(
                [node, "--check", str(ROOT / "js" / name)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)
        script = r"""
import { loraNamesFromInfo, loraNamesFromModels } from "./js/s1_model.js";

function assert(cond, message) {
  if (!cond) {
    console.error(message);
    process.exit(1);
  }
}

const wrapped = {
  LoraLoader: {
    input: {
      required: {
        lora_name: [["a.safetensors", "sub/b.safetensors", "a.safetensors"], { tooltip: "x" }],
      },
    },
  },
};
assert(
  JSON.stringify(loraNamesFromInfo(wrapped)) === JSON.stringify(["a.safetensors", "sub/b.safetensors"]),
  "wrapped LoraLoader list",
);

const modelOnly = {
  LoraLoaderModelOnly: {
    input: { required: { lora_name: [["only.safetensors"], {}] } },
  },
};
assert(
  JSON.stringify(loraNamesFromInfo(modelOnly)) === JSON.stringify(["only.safetensors"]),
  "LoraLoaderModelOnly",
);

const direct = { input: { required: { lora_name: [["direct.safetensors"]] } } };
assert(
  JSON.stringify(loraNamesFromInfo(direct)) === JSON.stringify(["direct.safetensors"]),
  "direct node info",
);

const empty = { LoraLoader: { input: { required: { lora_name: [[], {}] } } } };
assert(JSON.stringify(loraNamesFromInfo(empty)) === "[]", "empty list");
assert(loraNamesFromInfo({ CheckpointLoaderSimple: {} }) === null, "missing loader");
assert(loraNamesFromInfo(null) === null, "null payload");

const combo = { input: { required: { lora_name: ["COMBO", { options: ["c.safetensors"] }] } } };
assert(JSON.stringify(loraNamesFromInfo(combo)) === JSON.stringify(["c.safetensors"]), "combo options");

assert(
  JSON.stringify(
    loraNamesFromModels(["m.safetensors", { name: "n.safetensors" }, { filename: "o.safetensors" }, 3]),
  ) === JSON.stringify(["m.safetensors", "n.safetensors", "o.safetensors"]),
  "models payload",
);
assert(loraNamesFromModels({ files: [] }) === null, "models object is not a list");
console.log("ok");
"""
        completed = subprocess.run(
            [node, "--input-type=module", "--eval", script],
            check=False,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("ok", completed.stdout)

    def test_editor_model_assigns_lora_ids_and_shares_strength(self):
        model_js = (ROOT / "js" / "s1_model.js").read_text(encoding="utf-8")
        self.assertIn("export function nextLoraId", model_js)
        self.assertIn("export function assignLoraIds", model_js)
        self.assertIn("strength_model: strength", model_js)
        self.assertIn("strength_clip: strength", model_js)
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        script = r"""
import { assignLoraIds, blankLora, commitModel, nextLoraId } from "./js/s1_model.js";

function assert(cond, message) {
  if (!cond) {
    console.error(message);
    process.exit(1);
  }
}

assert(nextLoraId([]) === "lora_1", "empty -> lora_1");
assert(nextLoraId(["lora_1", "lora_3"]) === "lora_2", "fill the gap");
assert(nextLoraId(["style_anime_v3", "lora_1"]) === "lora_2", "manual id stays out of the sequence");
assert(nextLoraId(["lora_0", "lora_01", "Lora_1"]) === "lora_1", "only exact lora_N is taken");

const created = blankLora();
assert(created.lora_id === "", "blank id is filled later");
assert(created.strength_model === 0.8 && created.strength_clip === 0.8, "blank strengths match");

const model = {
  loras: [
    { lora_id: "", name: "new.safetensors", strength_model: 0.2, strength_clip: 0.9 },
    { lora_id: "style_anime_v3", name: "a.safetensors", strength_model: 0.8, strength_clip: 0.4 },
    { lora_id: "lora_1", name: "b.safetensors", strength_model: 0.5, strength_clip: 0.5 },
    blankLora(),
    { lora_id: "   ", name: "blank.safetensors", strength_model: 1, strength_clip: 1 },
  ],
};
assignLoraIds(model);
assert(model.loras[0].lora_id === "lora_2", "blank does not collide with later lora_1");
assert(model.loras[1].lora_id === "style_anime_v3", "manual id kept");
assert(model.loras[2].lora_id === "lora_1", "lora_1 kept");
assert(model.loras[3].lora_id === "lora_3", "blankLora filled");
assert(model.loras[4].lora_id === "lora_4", "whitespace id replaced");
assert(model.loras[1].strength_clip === 0.4, "assignLoraIds does not rewrite strengths");

const applied = commitModel("lora", {
  loras: [
    { lora_id: "style_anime_v3", name: "a.safetensors", strength_model: 0.85, strength_clip: 0.2, tags: ["style"], enabled_default: false, meta: { note: "x" } },
    { lora_id: "", name: "new.safetensors", strength: "0.6", strength_model: 0.1, strength_clip: 0.1 },
    { name: "also.safetensors", strength_model: 0.3, strength_clip: 0.9 },
  ],
});
assert(applied.ok, applied.error || "commit failed");
assert(applied.doc.loras[0].lora_id === "style_anime_v3", "commit keeps manual id");
assert(applied.doc.loras[0].strength_model === 0.85 && applied.doc.loras[0].strength_clip === 0.85, "prefer strength_model");
assert(applied.doc.loras[0].tags[0] === "style", "tags kept");
assert(applied.doc.loras[0].enabled_default === false, "enabled_default kept");
assert(applied.doc.loras[0].meta.note === "x", "meta kept");
assert(applied.doc.loras[1].lora_id === "lora_1", "blank filled on commit");
assert(applied.doc.loras[1].strength_model === 0.6 && applied.doc.loras[1].strength_clip === 0.6, "editor strength field");
assert(applied.doc.loras[2].lora_id === "lora_2", "missing id filled on commit");
assert(applied.doc.loras[2].strength_model === 0.3 && applied.doc.loras[2].strength_clip === 0.3, "strength_model copied to clip");
for (const entry of applied.doc.loras) {
  assert(!Object.prototype.hasOwnProperty.call(entry, "strength"), "stored JSON has no strength key");
}
assert(applied.model.loras[1].lora_id === "lora_1", "returned editor model has the new id");
assert(applied.model.loras[1].strength === undefined, "returned model drops the editor strength field");
assert(!applied.json.includes('\n    "strength":'), "pretty JSON has no strength key");

const themed = commitModel("theme", {
  themes: [{
    theme_id: "t",
    title: "t",
    instructions: "i",
    select_mode: "single",
    options: [{
      option_id: "o",
      label: "o",
      description: "",
      lora_bindings: [{ lora_id: "style_anime_v3", strength_model: 0.2, strength_clip: 0.4 }],
    }],
  }],
});
assert(themed.ok, themed.error || "theme commit failed");
const binding = themed.doc.themes[0].options[0].lora_bindings[0];
assert(binding.lora_id === "style_anime_v3", "binding id kept");
assert(binding.strength_model === 0.2 && binding.strength_clip === 0.4, "binding strengths stay independent");

const missing = commitModel("lora", { loras: [{ lora_id: "a", name: "a.safetensors" }] });
assert(!missing.ok, "missing strength is rejected");
console.log("ok");
"""
        completed = subprocess.run(
            [node, "--input-type=module", "--eval", script],
            check=False,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("ok", completed.stdout)

    def test_editor_model_assigns_theme_and_option_ids(self):
        model_js = (ROOT / "js" / "s1_model.js").read_text(encoding="utf-8")
        self.assertIn("export function nextThemeId", model_js)
        self.assertIn("export function nextOptionId", model_js)
        self.assertIn("export function assignThemeIds", model_js)
        self.assertIn("export function assignOptionIds", model_js)
        self.assertIn("export function fieldPathsFromError", model_js)
        self.assertNotIn("fallback_option_id", model_js)
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        script = r"""
import {
  assignOptionIds,
  assignThemeIds,
  blankOption,
  blankTheme,
  commitModel,
  fieldPathsFromError,
  nextOptionId,
  nextThemeId,
  parseEditorDocument,
} from "./js/s1_model.js";

function assert(cond, message) {
  if (!cond) {
    console.error(message);
    process.exit(1);
  }
}

assert(nextThemeId([]) === "theme_1", "empty theme");
assert(nextThemeId(["theme_1", "theme_3"]) === "theme_2", "theme gap");
assert(nextThemeId(["art_style", "theme_1"]) === "theme_2", "manual theme stays out");
assert(nextOptionId([]) === "option_1", "empty option");
assert(nextOptionId(["option_1", "anime"]) === "option_2", "manual option stays out");
assert(nextOptionId(["option_0", "Option_1"]) === "option_1", "only exact option_N is taken");

const created = blankTheme();
assert(created.theme_id === "", "blank theme id is filled later");
assert(!Object.prototype.hasOwnProperty.call(created, "fallback_option_id"), "blank theme has no fallback");
assert(created.none_option_id === "", "none stays on the blank theme");
assert(blankOption().option_id === "", "blank option id is filled later");

const draft = {
  themes: [
    blankTheme(),
    {
      theme_id: "theme_2",
      title: "",
      instructions: "",
      select_mode: "single",
      options: [blankOption(), { option_id: "anime", label: "", description: "", lora_bindings: [] }],
    },
  ],
};
assignThemeIds(draft);
assert(draft.themes[0].theme_id === "theme_1", "first blank theme takes theme_1");
assert(draft.themes[1].theme_id === "theme_2", "theme_2 kept");
assert(draft.themes[1].options[0].option_id === "option_1", "blank option filled inside its theme");
assert(draft.themes[1].options[1].option_id === "anime", "manual option kept");

const perTheme = { options: [{ option_id: "" }, { option_id: "anime" }] };
assignOptionIds(perTheme.options);
assignOptionIds([{ option_id: "" }]);
assert(perTheme.options[0].option_id === "option_1", "option ids do not leak across lists");

const filled = commitModel("theme", {
  themes: [
    {
      theme_id: "",
      title: "A",
      instructions: "i",
      select_mode: "single",
      options: [
        { option_id: "anime", label: "a", description: "", lora_bindings: [] },
        { option_id: "", label: "b", description: "", lora_bindings: [] },
        { option_id: "option_1", label: "c", description: "", lora_bindings: [] },
      ],
    },
    {
      theme_id: "theme_1",
      title: "B",
      instructions: "i",
      select_mode: "multi",
      none_option_id: "option_1",
      options: [{ option_id: "   ", label: "d", description: "", lora_bindings: [] }],
    },
  ],
});
assert(filled.ok, filled.error || "theme commit failed");
assert(filled.doc.themes[0].theme_id === "theme_2", "blank theme fills the gap");
assert(filled.doc.themes[0].options[0].option_id === "anime", "commit keeps manual option");
assert(filled.doc.themes[0].options[1].option_id === "option_2", "blank option skips kept option_1");
assert(filled.doc.themes[0].options[2].option_id === "option_1", "option_1 kept");
assert(filled.doc.themes[1].theme_id === "theme_1", "commit keeps theme_1");
assert(filled.doc.themes[1].options[0].option_id === "option_1", "option ids restart inside the theme");
assert(filled.doc.themes[1].none_option_id === "option_1", "none kept");
assert(!JSON.stringify(filled.doc).includes("fallback_option_id"), "emit omits fallback");

const manual = commitModel("theme", {
  themes: [{
    theme_id: "art_style",
    title: "t",
    instructions: "i",
    select_mode: "single",
    none_option_id: "realistic",
    options: [
      { option_id: "anime", label: "a", description: "", lora_bindings: [] },
      { option_id: "realistic", label: "r", description: "", lora_bindings: [] },
    ],
  }],
});
assert(manual.ok, manual.error || "manual theme failed");
assert(manual.doc.themes[0].theme_id === "art_style", "manual theme id kept");
assert(manual.doc.themes[0].none_option_id === "realistic", "none still emitted");

const stale = parseEditorDocument("theme", JSON.stringify({
  themes: [{
    theme_id: "art_style",
    title: "t",
    instructions: "i",
    select_mode: "single",
    fallback_option_id: "realistic",
    options: [{ option_id: "realistic", label: "r", description: "", lora_bindings: [] }],
  }],
}));
assert(!stale.ok, "fallback_option_id is rejected");
assert(String(stale.error).includes("fallback_option_id"), stale.error || "missing fallback error");
assert(String(stale.error).includes("unknown field"), stale.error || "missing unknown-field error");

const empty = commitModel("theme", { themes: [blankTheme()] });
assert(!empty.ok, "empty theme is not written");

const sequence = commitModel("sequence", {
  steps: [{ step_id: "s1", theme_id: "art_style", enabled_by_default: true, dependencies: [] }],
});
assert(sequence.ok, sequence.error || "sequence commit failed");
assert(sequence.doc.steps[0].theme_id === "art_style", "step theme_id is not auto-rewritten");

assert(
  JSON.stringify(fieldPathsFromError("themes[0].title must be a non-empty string")) ===
    JSON.stringify(["themes.0.title"]),
  "title path",
);
assert(
  JSON.stringify(fieldPathsFromError("themes[0]: duplicate theme_id theme_1")) ===
    JSON.stringify(["themes.0", "themes.0.theme_id"]),
  "duplicate theme id",
);
assert(
  JSON.stringify(fieldPathsFromError("themes[0].options[1]: duplicate option_id option_1")) ===
    JSON.stringify(["themes.0.options.1", "themes.0.options.1.option_id"]),
  "duplicate option id",
);
assert(
  JSON.stringify(fieldPathsFromError("themes[0]: none_option_id foo is not an option of this theme")) ===
    JSON.stringify(["themes.0", "themes.0.none_option_id"]),
  "none path",
);
assert(
  JSON.stringify(fieldPathsFromError("steps[0].dependencies[0].when: op eq requires exactly one option_id")) ===
    JSON.stringify(["steps.0.dependencies.0.when", "steps.0.dependencies.0.when.option_ids"]),
  "when option_ids",
);
assert(
  JSON.stringify(fieldPathsFromError("steps[0].dependencies[0].actions[0]: rewrite_options JSON is invalid")) ===
    JSON.stringify(["steps.0.dependencies.0.actions.0", "steps.0.dependencies.0.actions.0.rewrite_json"]),
  "rewrite json path",
);
assert(JSON.stringify(fieldPathsFromError("Invalid JSON: nope")) === "[]", "unmapped error has no field");
console.log("ok");
"""
        completed = subprocess.run(
            [node, "--input-type=module", "--eval", script],
            check=False,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("ok", completed.stdout)

    def test_lora_library_editor_shows_readonly_id_and_one_strength(self):
        editors = (ROOT / "js" / "s1_editors.js").read_text(encoding="utf-8")
        start = editors.index("function renderLoras()")
        end = editors.index("function renderBinding(")
        body = editors[start:end]
        self.assertNotIn('field("lora_id"', body)
        self.assertNotIn('field("strength_model"', body)
        self.assertNotIn('field("strength_clip"', body)
        self.assertIn('readOnlyLine("lora_id"', body)
        self.assertIn("LoRA ${index + 1} · ${entry.lora_id}", body)
        self.assertIn("strength (model & clip)", body)
        self.assertIn("${path}.strength", body)
        self.assertIn("assignLoraIds(state.model)", editors)
        readonly_start = editors.index("function readOnlyLine(")
        readonly_end = editors.index("function displayedStrength(")
        readonly = editors[readonly_start:readonly_end]
        self.assertIn("input.readOnly = true", readonly)
        self.assertNotIn("dataset.path", readonly)
        binding_end = editors.index("function renderOption(")
        binding = editors[end:binding_end]
        self.assertIn('field("lora_id"', binding)
        self.assertIn('field("strength_model"', binding)
        self.assertIn('field("strength_clip"', binding)
        self.assertIn("Blank strengths use the LoRA Library defaults.", binding)
        node = shutil.which("node")
        if node is None:
            return
        checked = subprocess.run(
            [node, "--check", str(ROOT / "js" / "s1_editors.js")],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_sequence_editor_puts_negative_prompt_under_positive(self):
        editors = (ROOT / "js" / "s1_editors.js").read_text(encoding="utf-8")
        positive_at = editors.index('promptField("positive"')
        negative_at = editors.index('promptField("negative"')
        self.assertLess(positive_at, negative_at)
        self.assertIn("Positive prompt", editors)
        self.assertIn("Negative prompt", editors)
        self.assertIn("writePromptWidgets", editors)
        self.assertIn("sequence_json", editors)
        self.assertNotIn("S1_THEME_SEQ", editors)
        description = PKG.NODE_CLASS_MAPPINGS["S1ThemeSequence"].DESCRIPTION
        self.assertIn("positive", description)
        self.assertIn("negative", description)
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        checked = subprocess.run(
            [node, "--check", str(ROOT / "js" / "s1_editors.js")],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_nodes_run_example_and_passthrough_errors(self):
        lora_node = PKG.NODE_CLASS_MAPPINGS["S1LoraLibrary"]()
        theme_node = PKG.NODE_CLASS_MAPPINGS["S1ThemeLibrary"]()
        sequence_node = PKG.NODE_CLASS_MAPPINGS["S1ThemeSequence"]()
        (lora_lib,) = lora_node.build(_read("lora_library.minimal.json"))
        (theme_lib,) = theme_node.build(_read("theme_library.minimal.json"))
        model = object()
        clip = object()
        with mock.patch("urllib.request.urlopen", side_effect=_canned_urlopen):
            out_model, out_clip, report_json = sequence_node.apply(
                model=model,
                theme_lib=theme_lib,
                lora_lib=lora_lib,
                positive="anime",
                sequence_json=_read("sequence.minimal.json"),
                api_key="sekret-token-xyz",
                api_model="my-model",
                clip=clip,
            )
        self.assertIs(out_model, model)
        self.assertIs(out_clip, clip)
        report = json.loads(report_json)
        self.assertEqual(report["answers"]["s1"]["selected"], ["anime"])
        self.assertEqual(report["answers"]["s2"]["selected"], ["waifu_a"])
        self.assertEqual(report["api"]["model"], "my-model")
        self.assertFalse(report["stub"])
        self.assertNotIn("sekret-token-xyz", report_json)
        self.assertIn('"answers":{', report_json)

        untouched = object()
        same_model, same_clip, error_json = sequence_node.apply(
            model=untouched,
            theme_lib=theme_lib,
            lora_lib=lora_lib,
            positive="",
            sequence_json="{",
            api_key="",
            api_model="",
        )
        self.assertIs(same_model, untouched)
        self.assertIsNone(same_clip)
        error_report = json.loads(error_json)
        self.assertTrue(error_report["errors"])
        self.assertIn("passthrough", " ".join(error_report["notes"]))
        with self.assertRaises(TYPES.SchemaError):
            lora_node.build("{")
        with self.assertRaises(Exception):
            sequence_node.apply(
                model=untouched,
                theme_lib=theme_lib,
                lora_lib=lora_lib,
                positive="",
                sequence_json="{",
                api_key="",
                api_model="",
                on_error="raise",
            )

    def test_negative_under_positive_reaches_state(self):
        lora_node = PKG.NODE_CLASS_MAPPINGS["S1LoraLibrary"]()
        theme_node = PKG.NODE_CLASS_MAPPINGS["S1ThemeLibrary"]()
        sequence_node = PKG.NODE_CLASS_MAPPINGS["S1ThemeSequence"]()
        (lora_lib,) = lora_node.build(_read("lora_library.minimal.json"))
        (theme_lib,) = theme_node.build(_read("theme_library.minimal.json"))
        seen = []

        def urlopen(req, timeout=None):
            seen.append(_payload_from_request(req)["state"])
            return _canned_urlopen(req, timeout)

        def run(**extra):
            seen.clear()
            with mock.patch("urllib.request.urlopen", side_effect=urlopen):
                sequence_node.apply(
                    model=object(),
                    theme_lib=theme_lib,
                    lora_lib=lora_lib,
                    positive="anime",
                    sequence_json=_read("sequence.minimal.json"),
                    api_key="sekret-token-xyz",
                    api_model="my-model",
                    **extra,
                )
            self.assertTrue(seen)
            return seen

        self.assertTrue(all(item == {"positive": "anime", "negative": "blurry"} for item in run(negative="blurry")))
        self.assertTrue(all(item == {"positive": "anime", "negative": ""} for item in run()))
        self.assertTrue(all(item == {"positive": "anime", "negative": ""} for item in run(negative="")))
        self.assertTrue(all(item == {"positive": "anime", "negative": ""} for item in run(negative=None)))

    def test_comfyui_loader_style_import(self):
        script = (
            "import importlib.util, os, sys\n"
            "root = sys.argv[1]\n"
            "name = root.replace('.', '_x_')\n"
            "init = os.path.join(root, '__init__.py')\n"
            "spec = importlib.util.spec_from_file_location(name, init)\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "sys.modules[name] = mod\n"
            "spec.loader.exec_module(mod)\n"
            "print(','.join(sorted(mod.NODE_CLASS_MAPPINGS)))\n"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script, str(ROOT)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout.strip(),
            "S1LoraLibrary,S1ThemeLibrary,S1ThemeSequence",
        )


if __name__ == "__main__":
    unittest.main()
