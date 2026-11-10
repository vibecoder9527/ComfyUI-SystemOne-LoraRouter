"""Theme option ids follow table order ("swap position" semantics).

The frontend canonicalizes theme_json so option_N is table row N and
backend slot N-1, None last, and moves graph.links with the options. The
backend still maps slot i to theme.options[i] and never reorders, so wires
stay valid for any document (canonical or legacy). These tests pin that
contract and run the pure JS checks in tests/js/ with node when available.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from tests.harness import (
    PKG,
    ROOT,
    TYPES,
    FakeHTTPResponse,
    make_settings,
    payload_from_request,
)

BLOCKER = __import__(PKG.__name__ + ".schema.blocker", fromlist=["blocker"])
NONE = __import__(PKG.__name__ + ".schema.none_option", fromlist=["none_option"])

FIXTURE = Path(__file__).parent / "fixtures" / "user_theme_collect_sanitized.json"
JS_TEST = Path(__file__).parent / "js" / "theme_reorder_ids.test.mjs"
ROOT_NODE_ID = "87:86"


def _choice_urlopen(choice_id, seen=None):
    def urlopen(req, timeout=None):
        body = payload_from_request(req)
        if seen is not None:
            seen.append(body)
        answers = {}
        for qid, question in body["questions"].items():
            if question.get("type") == "choice":
                answers[qid] = {"choice": choice_id, "confidence": 1.0}
            else:
                option_id = qid.split("__", 1)[1]
                answers[qid] = {"noul": 1.0 if option_id == choice_id else 0.0}
        return FakeHTTPResponse({"model": body.get("model"), "answers": answers})

    return urlopen


def _theme(options, none_option_id=None, theme_id="theme_1"):
    doc = {
        "version": 1,
        "theme_id": theme_id,
        "title": "Theme",
        "instructions": "Choose the clothing.",
        "select_mode": "single",
        "options": options,
    }
    if none_option_id:
        doc["none_option_id"] = none_option_id
    return doc


def _opt(option_id, label, tags=None):
    item = {"option_id": option_id, "label": label, "description": label}
    if tags:
        item["tags"] = list(tags)
    return item


def _decide(theme_json, choice_id, seen=None):
    root = PKG.NODE_CLASS_MAPPINGS["S1ThemeRoot"]()
    with mock.patch("urllib.request.urlopen", side_effect=_choice_urlopen(choice_id, seen)):
        return root.decide(
            positive="a girl at the beach",
            negative="",
            settings=make_settings(),
            theme_json=json.dumps(theme_json),
        )


def _run_node(script):
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node is not installed")
    completed = subprocess.run(
        [node, "--input-type=module", "--eval", script],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stdout + completed.stderr)
    return completed.stdout


class BackendSlotMappingTests(unittest.TestCase):
    """Slot i is options[i]; option ids are copied into report_json verbatim."""

    def test_canonical_theme_option_n_is_slot_n_minus_1(self):
        doc = _theme(
            [_opt("option_1", "bikini", ["bikini"]), _opt("option_2", "dress", ["dress"]), _opt("option_3", "None")],
            "option_3",
        )
        out = _decide(doc, "option_2")
        self.assertEqual(len(out), TYPES.MAX_OPTION_OUTPUTS + 1)
        self.assertTrue(BLOCKER.is_execution_blocker(out[0]))
        self.assertEqual(out[1].slot_option_id, "option_2")
        self.assertEqual(out[1].result.tags, ["dress"])
        self.assertTrue(BLOCKER.is_execution_blocker(out[2]))
        report = json.loads(out[-1])
        self.assertEqual(
            [slot["option_id"] for slot in report["slots"]],
            ["option_1", "option_2", "option_3"],
        )
        self.assertEqual(report["slots"][1]["emitted"], "selected")

    def test_canonical_none_last_is_recognized_and_not_duplicated(self):
        doc = _theme([_opt("option_1", "bikini", ["bikini"]), _opt("option_2", "None")], "option_2")
        ensured = NONE.ensure_default_none_option(doc)
        self.assertEqual(ensured["none_option_id"], "option_2")
        self.assertEqual(len(ensured["options"]), 2)
        parsed = TYPES.parse_theme_for_run(json.dumps(doc))
        self.assertEqual([item.option_id for item in parsed.options], ["option_1", "option_2"])
        self.assertEqual(parsed.none_option_id, "option_2")
        out = _decide(doc, "option_2")
        self.assertEqual(out[1].slot_option_id, "option_2")
        self.assertEqual(out[1].result.tags, [], "None contributes no tags")

    def test_legacy_order_still_maps_by_array_index(self):
        # A document that was never normalized (e.g. API-only use) keeps its
        # saved slot indexes: the backend does not reorder or renumber.
        legacy = _theme(
            [_opt("option_1", "bikini", ["bikini"]), _opt("option_2", "None"), _opt("option_3", "dress", ["dress"])],
            "option_2",
        )
        out = _decide(legacy, "option_3")
        self.assertEqual(out[2].slot_option_id, "option_3")
        self.assertEqual(out[2].result.tags, ["dress"])
        self.assertTrue(BLOCKER.is_execution_blocker(out[1]))
        report = json.loads(out[-1])
        self.assertEqual([slot["option_id"] for slot in report["slots"]], ["option_1", "option_2", "option_3"])

    def test_report_ids_are_whatever_theme_json_had_at_run_time(self):
        # Old report_json files keep their old ids; nothing reads them back.
        legacy = _theme([_opt("option_1", "bikini"), _opt("option_2", "None"), _opt("option_3", "dress")], "option_2")
        canonical = _theme([_opt("option_1", "bikini"), _opt("option_2", "dress"), _opt("option_3", "None")], "option_3")
        old_report = json.loads(_decide(legacy, "option_3")[-1])
        new_report = json.loads(_decide(canonical, "option_2")[-1])
        old_selected = [slot["option_id"] for slot in old_report["slots"] if slot["emitted"] == "selected"]
        new_selected = [slot["option_id"] for slot in new_report["slots"] if slot["emitted"] == "selected"]
        self.assertEqual(old_selected, ["option_3"])
        self.assertEqual(new_selected, ["option_2"], "same choice (dress), new id = its table row")

    def test_llm_criteria_follow_canonical_order(self):
        seen = []
        doc = _theme([_opt("option_1", "bikini"), _opt("option_2", "dress"), _opt("option_3", "None")], "option_3")
        _decide(doc, "option_1", seen)
        criteria = seen[0]["questions"]["theme_1"]["criteria"]
        self.assertEqual(list(criteria), ["option_1", "option_2", "option_3"])
        self.assertNotIn("tags", json.dumps(seen[0]["questions"]))


class FrontendNormalizationTests(unittest.TestCase):
    def test_js_reorder_suite(self):
        if shutil.which("node") is None:
            self.skipTest("node is not installed")
        completed = subprocess.run(
            [shutil.which("node"), str(JS_TEST)],
            check=False,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertTrue(completed.stdout.startswith("ok "), completed.stdout)

    def test_sanitized_fixture_legacy_order_normalizes_and_runs(self):
        # The user's sanitized prompt: bikini=option_1, None=option_2, with
        # Collect a<-slot 0 and b<-slot 1. Add dress the old way (appended
        # as option_3 after None), normalize in JS, remap the API links,
        # and run the backend on the result.
        prompt = json.loads(FIXTURE.read_text(encoding="utf-8"))
        root = prompt[ROOT_NODE_ID]
        legacy = json.loads(root["inputs"]["theme_json"])
        legacy["options"].append(_opt("option_3", "dress", ["dress"]))
        script = (
            "import { planThemeWrite, parseEditorDocument } from './js/s1_model.js';\n"
            f"const previous = {json.dumps(json.dumps(legacy))};\n"
            "const parsed = parseEditorDocument('theme', previous);\n"
            "const planned = planThemeWrite(previous, parsed.model);\n"
            "console.log(JSON.stringify({ ok: planned.ok, json: planned.json, changed: planned.changed,"
            " map: [...planned.remap.indexMap.entries()], removed: planned.remap.removed }));\n"
        )
        result = json.loads(_run_node(script).strip().splitlines()[-1])
        self.assertTrue(result["ok"] and result["changed"])
        index_map = {int(k): int(v) for k, v in result["map"]}
        self.assertEqual(index_map, {0: 0, 1: 2, 2: 1})
        self.assertEqual(result["removed"], [])
        canonical = json.loads(result["json"])
        self.assertEqual([o["label"] for o in canonical["options"]], ["bikini", "dress", "None"])
        self.assertEqual([o["option_id"] for o in canonical["options"]], ["option_1", "option_2", "option_3"])
        self.assertEqual(canonical["none_option_id"], "option_3")

        # Remap API-format links that point at the root's option slots.
        for node in prompt.values():
            for name, value in list(node["inputs"].items()):
                if isinstance(value, list) and len(value) == 2 and value[0] == ROOT_NODE_ID:
                    if value[1] in index_map:
                        node["inputs"][name] = [ROOT_NODE_ID, index_map[value[1]]]
        self.assertEqual(prompt["87:88"]["inputs"]["b"], [ROOT_NODE_ID, 2], "Collect b stays on None")
        self.assertEqual(prompt["87:88"]["inputs"]["a"], [ROOT_NODE_ID, 0], "Collect a stays on bikini")

        out = _decide(canonical, "option_3")
        self.assertEqual(out[2].slot_option_id, "option_3", "None now emits on slot 2 (option_3)")
        self.assertEqual(out[2].result.tags, [])
        out = _decide(canonical, "option_2")
        self.assertEqual(out[1].slot_option_id, "option_2")
        self.assertEqual(out[1].result.tags, ["dress"])

    def test_theme_node_writer_uses_remap(self):
        theme_node = (ROOT / "js" / "s1_theme_node.js").read_text(encoding="utf-8")
        editors = (ROOT / "js" / "s1_editors.js").read_text(encoding="utf-8")
        model_js = (ROOT / "js" / "s1_model.js").read_text(encoding="utf-8")
        write = theme_node[theme_node.index("function writeTheme(") : theme_node.index("function closeMenus(")]
        self.assertIn("planThemeWrite(previous, model)", write)
        self.assertIn("applyOptionIndexRemap(node, remap)", write)
        self.assertLess(write.index("applyOptionIndexRemap"), write.index("relinkOptionSlots"))
        plan = editors[editors.index("function applyThemePlan(") : editors.index("function syncOptionOutputs(")]
        self.assertIn("planThemeWrite(", plan)
        self.assertIn("applyOptionIndexRemap(node, remap)", plan)
        remap = model_js[model_js.index("export function applyOptionIndexRemap(") : model_js.index("export function planThemeWrite(")]
        self.assertNotIn("output.links =", remap)
        self.assertNotIn(".links = ", remap)
        self.assertIn("graph.removeLink", model_js)


if __name__ == "__main__":
    unittest.main()
