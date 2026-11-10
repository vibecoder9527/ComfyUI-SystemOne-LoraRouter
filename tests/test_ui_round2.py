"""UI-round-2: default None option, Collect dynamic inputs, sanitized workflow migration."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from tests.harness import (
    PKG,
    TYPES,
    CountingClient,
    as_payload,
    option,
    run_theme,
    theme_doc,
)

NONE = __import__(PKG.__name__ + ".schema.none_option", fromlist=["none_option"])
COLLECT_MOD = __import__(PKG.__name__ + ".nodes.theme_collect", fromlist=["theme_collect"])
AGG = __import__(PKG.__name__ + ".aggregate", fromlist=["aggregate"])
COMPAT = __import__(PKG.__name__ + ".schema.execution_compat", fromlist=["execution_compat"])

FIXTURE = Path(__file__).parent / "fixtures" / "user_theme_collect_sanitized.json"


class DefaultNoneOptionTests(unittest.TestCase):
    def test_reuses_none_like_option_without_shifting_indexes(self):
        document = {
            "version": 1,
            "theme_id": "theme_1",
            "title": "Theme",
            "instructions": "Choose.",
            "select_mode": "single",
            "options": [
                {"option_id": "option_1", "label": "bikini", "description": "bikini", "tags": ["bikini"]},
                {"option_id": "option_2", "label": "None", "description": "Not on the list"},
            ],
        }
        ensured = NONE.ensure_default_none_option(document)
        self.assertEqual(ensured["none_option_id"], "option_2")
        self.assertEqual([item["option_id"] for item in ensured["options"]], ["option_1", "option_2"])
        self.assertIsNone(document.get("none_option_id"))

    def test_appends_default_none_when_missing(self):
        document = {
            "options": [
                {"option_id": "option_1", "label": "bikini", "description": "bikini", "tags": ["bikini"]}
            ]
        }
        ensured = NONE.ensure_default_none_option(document)
        self.assertEqual(ensured["none_option_id"], "none")
        self.assertEqual(ensured["options"][0]["option_id"], "option_1")
        self.assertEqual(ensured["options"][1]["label"], "None")
        self.assertEqual(ensured["options"][1]["tags"], [])

    def test_parse_theme_for_run_adds_none_but_parse_theme_does_not(self):
        raw = theme_doc(options=[option("option_1", ["bikini"])])
        strict = TYPES.parse_theme(raw)
        self.assertEqual([item.option_id for item in strict.options], ["option_1"])
        self.assertIsNone(strict.none_option_id)
        for_run = TYPES.parse_theme_for_run(raw)
        self.assertEqual([item.option_id for item in for_run.options], ["option_1", "none"])
        self.assertEqual(for_run.none_option_id, "none")

    def test_one_user_option_plus_default_none_calls_api(self):
        client = CountingClient()
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = AssertionError("CountingClient should be used")
            outcome = run_theme(
                theme_json=theme_doc(options=[option("option_1", ["bikini"])]),
                client=client,
            )
        self.assertEqual(len(client.calls), 1)
        self.assertTrue(outcome.report["api"]["called"])

    def test_cannot_append_none_when_outputs_are_full(self):
        options = [{"option_id": f"option_{i}", "label": f"L{i}", "description": "d"} for i in range(TYPES.MAX_OPTION_OUTPUTS)]
        with self.assertRaises(TYPES.SchemaError) as ctx:
            NONE.ensure_default_none_option({"options": options})
        self.assertIn("capped", str(ctx.exception))


    def test_relabels_only_legacy_auto_generated_none_fields(self):
        legacy = NONE.LEGACY_DEFAULT_NONE_TEXT
        document = {
            "none_option_id": "option_2",
            "options": [
                {"option_id": "option_1", "label": legacy, "description": "user option", "tags": ["keep"]},
                {"option_id": "option_2", "label": legacy, "description": legacy, "tags": [legacy]},
            ],
        }
        original = document["options"][1]["label"]
        ensured = NONE.ensure_default_none_option(document)
        self.assertEqual(ensured["options"][1]["label"], "None")
        self.assertEqual(ensured["options"][1]["description"], "None")
        self.assertEqual(ensured["options"][1]["tags"], [legacy])
        self.assertEqual(ensured["options"][0]["label"], legacy)
        self.assertEqual(document["options"][1]["label"], original, "source document is copied, not mutated")

    def test_does_not_rewrite_custom_none_description(self):
        ensured = NONE.ensure_default_none_option({
            "none_option_id": "option_2",
            "options": [
                {"option_id": "option_1", "label": "bikini"},
                {"option_id": "option_2", "label": NONE.LEGACY_DEFAULT_NONE_TEXT, "description": "Not on the list", "tags": []},
            ],
        })
        self.assertEqual(ensured["options"][1]["label"], "None")
        self.assertEqual(ensured["options"][1]["description"], "Not on the list")

class ThemeCollectDynamicInputTests(unittest.TestCase):
    def test_declared_inputs_are_a_through_p(self):
        self.assertEqual(COLLECT_MOD.MAX_COLLECT_INPUTS, 16)
        self.assertEqual(COLLECT_MOD.COLLECT_INPUT_NAMES[0], "a")
        self.assertEqual(COLLECT_MOD.COLLECT_INPUT_NAMES[1], "b")
        self.assertEqual(len(COLLECT_MOD.COLLECT_INPUT_NAMES), 16)
        optional = PKG.NODE_CLASS_MAPPINGS["S1ThemeCollect"].INPUT_TYPES()["optional"]
        self.assertEqual(list(optional), list(COLLECT_MOD.COLLECT_INPUT_NAMES))

    def _branch(self, theme_id, option_id, tags):
        options = [option(option_id, list(tags))]
        if option_id != "none":
            options.append(option("none", []))
        result = run_theme(
            theme_json=theme_doc(
                theme_id=theme_id,
                none_option_id="none",
                options=options,
            ),
            client=CountingClient(),
        ).result
        return as_payload(result, slot_option_id=option_id)

    def test_collect_merges_more_than_two_branches(self):
        first = self._branch("theme_1", "option_1", ["bikini"])
        second = self._branch("theme_2", "none", [])
        third = self._branch("theme_3", "opt", ["other"])
        merged = AGG.collect_decisions(first, None, second, third)
        self.assertEqual([item.theme_id for item in merged.result.decisions], ["theme_1", "theme_2", "theme_3"])
        self.assertEqual(merged.result.tags, ["bikini", "other"])

        node = PKG.NODE_CLASS_MAPPINGS["S1ThemeCollect"]()
        (out,) = node.merge(a=first, c=second, d=third)
        self.assertEqual([item.theme_id for item in out.result.decisions], ["theme_1", "theme_2", "theme_3"])

    def test_collect_flag_and_hook_cover_extra_dynamic_keys(self):
        collect = PKG.NODE_CLASS_MAPPINGS["S1ThemeCollect"]()
        self.assertIs(type(collect).__dict__.get("IGNORE_OPTIONAL_EXECUTION_BLOCKERS"), True)
        live = object()

        class Blocker:
            pass

        Blocker.__name__ = "ExecutionBlocker"
        filtered = COMPAT.drop_optional_execution_blockers(
            collect,
            {"a": [live], "q": [Blocker()]},
            blocker_cls=Blocker,
        )
        self.assertEqual(list(filtered.keys()), ["a"])
        self.assertIs(filtered["a"][0], live)


class SanitizedUserWorkflowMigrationTests(unittest.TestCase):
    def test_user_theme_reuses_option_2_and_keeps_collect_links(self):
        self.assertTrue(FIXTURE.is_file())
        prompt = json.loads(FIXTURE.read_text(encoding="utf-8"))
        blob = FIXTURE.read_text(encoding="utf-8").lower()
        self.assertNotIn("api_key", blob)
        root = prompt["87:86"]
        collect = prompt["87:88"]
        self.assertEqual(root["class_type"], "S1ThemeRoot")
        self.assertEqual(collect["class_type"], "S1ThemeCollect")
        self.assertEqual(collect["inputs"]["a"], ["87:86", 0])
        self.assertEqual(collect["inputs"]["b"], ["87:86", 1])

        theme_json = root["inputs"]["theme_json"]
        document = json.loads(theme_json) if isinstance(theme_json, str) else theme_json
        self.assertIsNone(document.get("none_option_id"))
        self.assertEqual(document["options"][1]["option_id"], "option_2")
        ensured = NONE.ensure_default_none_option(document)
        self.assertEqual(ensured["none_option_id"], "option_2")
        self.assertEqual(len(ensured["options"]), 2)
        self.assertEqual(ensured["options"][0]["option_id"], "option_1")
        parsed = TYPES.parse_theme_for_run(document)
        self.assertEqual(parsed.none_option_id, "option_2")
        self.assertEqual([item.option_id for item in parsed.options], ["option_1", "option_2"])
        # Slot indexes used by Collect stay 0 and 1 after ensure.
        self.assertEqual(collect["inputs"]["a"][1], 0)
        self.assertEqual(collect["inputs"]["b"][1], 1)


if __name__ == "__main__":
    unittest.main()
