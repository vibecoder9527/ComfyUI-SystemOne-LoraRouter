"""SystemOne client tests. urllib is mocked. No live call and no real key."""

from __future__ import annotations

import io
import json
import os
import unittest
import urllib.error
import uuid
from unittest import mock

from tests.harness import CLIENT, FakeHTTPResponse, payload_from_request


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
            "art_style": {"type": "choice", "criteria": {"anime": "a", "real": "b"}},
            "character_pack__waifu_a": {"type": "noul"},
        }
        seen = {}

        def urlopen(req, timeout=None):
            seen["req"] = req
            seen["timeout"] = timeout
            body = payload_from_request(req)
            self.assertEqual(body["model"], CLIENT.SKELETON_MODEL_FALLBACK)
            self.assertEqual(list(body["state"]), ["positive", "negative"])
            self.assertEqual(body["state"], {"positive": "p", "negative": ""})
            self.assertEqual(set(body["questions"]), {"art_style", "character_pack__waifu_a"})
            return FakeHTTPResponse(
                {
                    "model": "live-model-echo",
                    "answers": {
                        "art_style": {
                            "type": "choice",
                            "choice": "anime",
                            "probabilities": {"anime": 0.9, "real": 0.1},
                            "confidence": 0.8,
                            "extra": "kept",
                        },
                        "character_pack__waifu_a": {"type": "noul", "noul": 0.7},
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
        self.assertEqual(result["answers"]["art_style"]["choice"], "anime")
        self.assertEqual(result["answers"]["art_style"]["confidence"], 0.8)
        self.assertEqual(result["model"], "live-model-echo")
        dumped = json.dumps(result)
        self.assertNotIn(secret, dumped)

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
            raise urllib.error.HTTPError(
                req.get_full_url(),
                401,
                "Unauthorized",
                {"X-System-One-Error-Code": "unauthorized"},
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

        with mock.patch("urllib.request.urlopen", return_value=FakeHTTPResponse({"answers": {}})):
            with self.assertRaises(CLIENT.SystemOneError) as ctx:
                client.decide(state, questions)
        self.assertIn("missing answers", str(ctx.exception))

    def test_decide_rejects_contract_errors_without_http(self):
        client = CLIENT.SystemOneClient(api_key="sekret-token-xyz", model="")
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

    def test_canned_answer_is_not_used_by_live_decide(self):
        source = CLIENT.__file__
        with open(source, encoding="utf-8") as handle:
            text = handle.read()
        decide_start = text.index("    def decide(")
        decide_end = text.index("\ndef _validate_request")
        body = text[decide_start:decide_end]
        self.assertNotIn("_canned_answer", body)


if __name__ == "__main__":
    unittest.main()
