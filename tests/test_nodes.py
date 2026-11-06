"""Node registration, widget order, mocked runs, and editor invariants."""

from __future__ import annotations

import importlib
import inspect
import json
import shutil
import subprocess
import sys
import unittest
from unittest import mock

from tests.harness import (
    APPLY,
    CLIENT,
    ENGINE,
    PKG,
    ROOT,
    TYPES,
    FakeHTTPResponse,
    canned_urlopen,
    lora_entries,
    option,
    payload_from_request,
    read_example,
    theme_doc,
)


JS_MODEL = r"""
import {
  assignLoraIds,
  assignOptionIds,
  assignThemeDocument,
  blankClause,
  blankLora,
  blankOption,
  commitModel,
  emptyThemeModel,
  fieldPathsFromError,
  loraNamesFromInfo,
  loraNamesFromModels,
  nextLoraId,
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

assert(nextLoraId([]) === "lora_1", "empty lora");
assert(nextLoraId(["lora_1", "lora_3"]) === "lora_2", "lora gap");
assert(nextLoraId(["style_anime_v3", "lora_1"]) === "lora_2", "manual lora");
assert(nextThemeId([]) === "theme_1", "empty theme");
assert(nextThemeId(["art_style"]) === "theme_1", "manual theme is not theme_N");
assert(nextOptionId(["option_1", "anime"]) === "option_2", "option gap");
assert(blankLora().lora_id === "", "blank lora id");
assert(blankOption().option_id === "", "blank option id");
assert(blankClause().op === "includes_any", "blank clause");
assert(!Object.prototype.hasOwnProperty.call(emptyThemeModel(), "fallback_option_id"), "no fallback");

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
assert(model.loras[0].lora_id === "lora_2", "blank skips lora_1");
assert(model.loras[1].lora_id === "style_anime_v3", "manual kept");
assert(model.loras[1].strength_clip === 0.4, "assign does not rewrite strength");

const applied = commitModel("lora", {
  loras: [
    { lora_id: "style_anime_v3", name: "a.safetensors", strength_model: 0.85, strength_clip: 0.2, tags: ["style"], enabled_default: false, meta: { note: "x" } },
    { lora_id: "", name: "new.safetensors", strength: "0.6", strength_model: 0.1, strength_clip: 0.1 },
    { name: "also.safetensors", strength_model: 0.3, strength_clip: 0.9 },
  ],
});
assert(applied.ok, applied.error || "lora commit failed");
assert(applied.doc.loras[0].strength_model === 0.85 && applied.doc.loras[0].strength_clip === 0.85, "strength_model copied");
assert(applied.doc.loras[1].strength_model === 0.6 && applied.doc.loras[1].strength_clip === 0.6, "editor strength");
assert(applied.doc.loras[2].lora_id === "lora_2", "missing id filled");
for (const entry of applied.doc.loras) {
  assert(!Object.prototype.hasOwnProperty.call(entry, "strength"), "no strength key");
}
assert(!applied.json.includes('\n    "strength":'), "pretty json has no strength");

const theme = commitModel("theme", {
  theme_id: "",
  title: "A",
  instructions: "i",
  select_mode: "single",
  options: [
    { option_id: "anime", label: "a", description: "", tags: ["style_anime"] },
    { option_id: "", label: "b", description: "" },
    { option_id: "option_1", label: "c", description: "" },
  ],
});
assert(theme.ok, theme.error || "theme commit failed");
assert(theme.doc.theme_id === "theme_1", "one document fills theme_1");
assert(theme.doc.options[0].option_id === "anime", "manual option kept");
assert(theme.doc.options[0].tags[0] === "style_anime", "tags kept");
assert(theme.doc.options[1].option_id === "option_2", "blank option skips option_1");
assert(theme.doc.options[2].option_id === "option_1", "option_1 kept");
assert(!JSON.stringify(theme.doc).includes("lora_bindings"), "theme json has no bindings");

const manual = commitModel("theme", {
  theme_id: "art_style",
  title: "t",
  instructions: "i",
  select_mode: "single",
  none_option_id: "none",
  options: [
    { option_id: "anime", label: "a", description: "", tags: ["style_anime"] },
    { option_id: "none", label: "n", description: "", tags: ["should_not_apply"] },
  ],
});
assert(manual.ok, manual.error || "manual theme failed");
assert(manual.doc.theme_id === "art_style", "manual theme id kept");
assert(manual.doc.none_option_id === "none", "none kept");

const stale = parseEditorDocument("theme", JSON.stringify({
  theme_id: "art_style",
  title: "t",
  instructions: "i",
  select_mode: "single",
  fallback_option_id: "anime",
  options: [{ option_id: "anime", label: "a", description: "" }],
}));
assert(!stale.ok, "fallback rejected");
assert(String(stale.error).includes("fallback_option_id was removed and is not applied"), stale.error || "");

const library = parseEditorDocument("theme", JSON.stringify({ themes: [] }));
assert(!library.ok, "theme library rejected");
assert(String(library.error).includes("one theme"), library.error || "");

const bindings = parseEditorDocument("theme", JSON.stringify({
  theme_id: "t",
  title: "t",
  instructions: "i",
  select_mode: "single",
  options: [{ option_id: "a", label: "a", description: "", lora_bindings: [] }],
}));
assert(!bindings.ok, "bindings rejected");
assert(String(bindings.error).includes("lora_bindings was removed"), bindings.error || "");

const bom = parseEditorDocument("enable", "\uFEFF" + JSON.stringify({ match: "any", clauses: [] }));
assert(bom.ok, bom.error || "bom enable");

const enable = commitModel("enable", {
  match: "all",
  clauses: [{ theme_id: "art_style", op: "includes_any", option_ids: "anime, realistic" }],
});
assert(enable.ok, enable.error || "enable commit");
assert(enable.doc.clauses[0].option_ids.join(",") === "anime,realistic", "option ids split");
const bare = commitModel("enable", { clauses: [{ theme_id: "art_style", op: "skipped" }] });
assert(bare.ok, bare.error || "bare op");
assert(!Object.prototype.hasOwnProperty.call(bare.doc.clauses[0], "option_ids"), "bare op omits option ids");
const badBare = parseEditorDocument("enable", JSON.stringify({
  clauses: [{ theme_id: "art_style", op: "skipped", option_ids: ["anime"] }],
}));
assert(!badBare.ok, badBare.error || "skipped rejects option ids");

assert(!commitModel("theme", emptyThemeModel()).ok, "empty title is not written");
const perTheme = [{ option_id: "" }, { option_id: "anime" }];
assignOptionIds(perTheme);
assignOptionIds([{ option_id: "" }]);
assert(perTheme[0].option_id === "option_1", "option ids stay in one list");
const single = { theme_id: "  ", title: "T", options: [{ option_id: "" }] };
assignThemeDocument(single);
assert(single.theme_id === "theme_1", "blank theme id is theme_1");
assert(single.options[0].option_id === "option_1", "blank option filled");

assert(JSON.stringify(fieldPathsFromError("options[1]: duplicate option_id option_1")) === JSON.stringify(["options.1", "options.1.option_id"]), "option path");
assert(JSON.stringify(fieldPathsFromError("loras[0]: duplicate lora_id lora_1")) === JSON.stringify(["loras.0", "loras.0.lora_id"]), "lora path");
assert(JSON.stringify(fieldPathsFromError("theme: none_option_id foo is not an option of this theme")) === JSON.stringify(["none_option_id"]), "none path");
assert(JSON.stringify(fieldPathsFromError("clauses[0]: op eq requires exactly one option_id")) === JSON.stringify(["clauses.0", "clauses.0.option_ids"]), "clause path");
assert(JSON.stringify(fieldPathsFromError("Invalid JSON: nope")) === "[]", "unmapped");

const wrapped = { LoraLoader: { input: { required: { lora_name: [["a.safetensors", "sub/b.safetensors", "a.safetensors"], {}] } } } };
assert(JSON.stringify(loraNamesFromInfo(wrapped)) === JSON.stringify(["a.safetensors", "sub/b.safetensors"]), "wrapped");
const direct = { input: { required: { lora_name: [["direct.safetensors"]] } } };
assert(JSON.stringify(loraNamesFromInfo(direct)) === JSON.stringify(["direct.safetensors"]), "direct");
assert(loraNamesFromInfo(null) === null, "null info");
assert(JSON.stringify(loraNamesFromModels(["m.safetensors", { name: "n.safetensors" }, { filename: "o.safetensors" }, 3])) === JSON.stringify(["m.safetensors", "n.safetensors", "o.safetensors"]), "models");
assert(loraNamesFromModels({ files: [] }) === null, "models object");
console.log("ok");
"""


class NodeTests(unittest.TestCase):
    def test_registration_and_widget_order(self):
        mappings = PKG.NODE_CLASS_MAPPINGS
        self.assertEqual(
            set(mappings),
            {"S1LoraLibrary", "S1Theme", "S1ThemeCollect", "S1LoraAggregate"},
        )
        self.assertEqual(
            PKG.NODE_DISPLAY_NAME_MAPPINGS,
            {
                "S1LoraLibrary": "LoRA Library",
                "S1Theme": "Theme",
                "S1ThemeCollect": "Theme Collect",
                "S1LoraAggregate": "LoRA Aggregate",
            },
        )
        self.assertEqual(PKG.WEB_DIRECTORY, "./js")
        for node in mappings.values():
            self.assertEqual(node.CATEGORY, "SystemOne/LoraRouter")
        theme = mappings["S1Theme"]
        self.assertEqual(theme.FUNCTION, "decide")
        self.assertEqual(theme.RETURN_TYPES, ("S1_THEME_RESULT", "STRING"))
        self.assertEqual(theme.RETURN_NAMES, ("theme_result", "report_json"))
        required = list(theme.INPUT_TYPES()["required"])
        self.assertEqual(
            required,
            ["positive", "negative", "theme_json", "run", "enable_json", "api_key", "api_model"],
        )
        self.assertEqual(required[required.index("positive") + 1], "negative")
        inputs = theme.INPUT_TYPES()
        self.assertEqual(inputs["required"]["negative"][1]["default"], "")
        self.assertTrue(inputs["required"]["negative"][1]["multiline"])
        self.assertEqual(inputs["required"]["run"][1]["default"], "disabled")
        self.assertEqual(inputs["required"]["run"][0], ["disabled", "enabled", "when_upstream"])
        self.assertFalse(inputs["required"]["theme_json"][1]["dynamicPrompts"])
        self.assertFalse(inputs["required"]["enable_json"][1]["dynamicPrompts"])
        self.assertEqual(inputs["required"]["theme_json"][1]["default"], TYPES.EMPTY_THEME_JSON)
        self.assertEqual(inputs["required"]["enable_json"][1]["default"], TYPES.EMPTY_ENABLE_JSON)
        self.assertEqual(
            set(inputs["optional"]),
            {"upstream", "endpoint", "noul_threshold", "on_error", "min_confidence"},
        )
        self.assertTrue(inputs["optional"]["upstream"][1]["forceInput"])
        self.assertEqual(inputs["optional"]["on_error"][1]["default"], "passthrough")
        self.assertEqual(inputs["optional"]["endpoint"][1]["default"], CLIENT.DEFAULT_ENDPOINT)
        signature = inspect.signature(theme.decide)
        params = list(signature.parameters)
        self.assertEqual(params[params.index("positive") + 1], "negative")
        self.assertIs(signature.parameters["negative"].default, inspect.Parameter.empty)
        self.assertIn("when_upstream", theme.DESCRIPTION)
        self.assertIn("visual editor", theme.DESCRIPTION.lower())

        library = mappings["S1LoraLibrary"]
        self.assertEqual(library.RETURN_TYPES, ("S1_LORA_LIB",))
        self.assertEqual(
            library.INPUT_TYPES()["required"]["library_json"][1]["default"],
            TYPES.EMPTY_LORA_LIBRARY_JSON,
        )
        self.assertFalse(library.INPUT_TYPES()["required"]["library_json"][1]["dynamicPrompts"])

        collect = mappings["S1ThemeCollect"]
        self.assertEqual(collect.FUNCTION, "merge")
        self.assertEqual(list(collect.INPUT_TYPES()["required"]), ["a", "b"])
        self.assertNotIn("optional", collect.INPUT_TYPES())
        self.assertTrue(collect.INPUT_TYPES()["required"]["a"][1]["forceInput"])

        aggregate = mappings["S1LoraAggregate"]
        self.assertEqual(aggregate.FUNCTION, "apply")
        self.assertEqual(aggregate.RETURN_TYPES, ("MODEL", "CLIP", "STRING"))
        self.assertEqual(list(aggregate.INPUT_TYPES()["required"]), ["model", "lora_lib", "theme_result"])
        self.assertEqual(set(aggregate.INPUT_TYPES()["optional"]), {"clip", "on_error"})
        self.assertFalse((ROOT / "sequence_engine.py").exists())
        self.assertFalse((ROOT / "nodes" / "theme_library.py").exists())
        self.assertFalse((ROOT / "nodes" / "theme_sequence.py").exists())
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("s1_lora_router.sequence_engine")

    def test_nodes_run_the_example_chain_without_a_live_api(self):
        lora_node = PKG.NODE_CLASS_MAPPINGS["S1LoraLibrary"]()
        theme_node = PKG.NODE_CLASS_MAPPINGS["S1Theme"]()
        aggregate = PKG.NODE_CLASS_MAPPINGS["S1LoraAggregate"]()
        collect = PKG.NODE_CLASS_MAPPINGS["S1ThemeCollect"]()
        (library,) = lora_node.build(read_example("lora_library.minimal.json"))
        seen = []

        def urlopen(req, timeout=None):
            seen.append(payload_from_request(req)["state"])
            return canned_urlopen(req, timeout)

        secret = "sekret-token-xyz"
        with mock.patch("urllib.request.urlopen", side_effect=urlopen):
            art, art_report = theme_node.decide(
                positive="anime girl",
                negative="blurry",
                theme_json=read_example("theme.art_style.json"),
                run="enabled",
                enable_json=read_example("enable.empty.json"),
                api_key=secret,
                api_model="my-model",
            )
            pack, pack_report = theme_node.decide(
                positive="child",
                negative="",
                theme_json=read_example("theme.character_pack.json"),
                run="when_upstream",
                enable_json=read_example("enable.when_anime.json"),
                api_key=secret,
                api_model="my-model",
                upstream=art,
            )
        self.assertEqual(seen[0], {"positive": "anime girl", "negative": "blurry"})
        self.assertEqual(seen[1], {"positive": "child", "negative": ""})
        self.assertEqual(art.get("art_style").selected, ["anime"])
        self.assertEqual(pack.tags, ["style_anime", "char_a", "char_b"])
        for report in (art_report, pack_report):
            self.assertNotIn(secret, report)
            self.assertIn('"api":{', report)
        model = object()
        out_model, out_clip, agg_report = aggregate.apply(model, library, pack)
        self.assertIs(out_model, model)
        self.assertIsNone(out_clip)
        parsed = json.loads(agg_report)
        self.assertEqual([item["lora_id"] for item in parsed["applied"]], ["char_a", "style_anime_v3"])
        self.assertEqual(parsed["matched"][1]["strength_model"], 0.8)
        self.assertNotEqual(parsed["matched"][1]["strength_model"], 0.85)
        with self.assertRaises(TYPES.SchemaError):
            collect.merge(art, pack)
        left, _left_report = theme_node.decide(
            positive="",
            negative="",
            theme_json=json.dumps(theme_doc(theme_id="left", options=[option("a", ["ta"])])),
            run="enabled",
            enable_json=TYPES.EMPTY_ENABLE_JSON,
            api_key="",
            api_model="",
        )
        right, _right_report = theme_node.decide(
            positive="",
            negative="",
            theme_json=json.dumps(theme_doc(theme_id="right", options=[option("b", ["tb"])])),
            run="enabled",
            enable_json=TYPES.EMPTY_ENABLE_JSON,
            api_key="",
            api_model="",
        )
        (merged,) = collect.merge(left, right)
        self.assertEqual([item.theme_id for item in merged.decisions], ["left", "right"])

        with mock.patch("urllib.request.urlopen") as urlopen_disabled:
            skipped, skipped_report = theme_node.decide(
                positive="",
                negative="",
                theme_json=read_example("theme.empty.json"),
                run="disabled",
                enable_json=read_example("enable.empty.json"),
                api_key=secret,
                api_model="",
            )
        urlopen_disabled.assert_not_called()
        self.assertEqual(skipped.get("theme_1").status, "skipped")
        self.assertNotIn(secret, skipped_report)
        self.assertFalse(json.loads(skipped_report)["api"]["called"])

        with mock.patch("urllib.request.urlopen") as urlopen_bad:
            with self.assertRaises(TYPES.SchemaError):
                theme_node.decide(
                    positive="",
                    negative="",
                    theme_json="{",
                    run="disabled",
                    enable_json=read_example("enable.empty.json"),
                    api_key="",
                    api_model="",
                    on_error="passthrough",
                )
        urlopen_bad.assert_not_called()

        def bad_choice(req, timeout=None):
            body = payload_from_request(req)
            answers = {
                qid: {"choice": "nope", "confidence": 1}
                for qid, question in body["questions"].items()
                if question["type"] == "choice"
            }
            return FakeHTTPResponse({"answers": answers})

        with mock.patch("urllib.request.urlopen", side_effect=bad_choice):
            with self.assertRaises(ENGINE.ThemeError):
                theme_node.decide(
                    positive="",
                    negative="",
                    theme_json=json.dumps(
                        theme_doc(
                            theme_id="bad_choice",
                            options=[option("a"), option("b")],
                        )
                    ),
                    run="enabled",
                    enable_json=read_example("enable.empty.json"),
                    api_key="k",
                    api_model="m",
                    on_error="raise",
                )

    def test_aggregate_node_passthrough_and_raise(self):
        node = PKG.NODE_CLASS_MAPPINGS["S1LoraAggregate"]()
        model = object()
        clip = object()
        out_model, out_clip, report = node.apply(model, "nope", "nope", clip=clip, on_error="passthrough")
        self.assertIs(out_model, model)
        self.assertIs(out_clip, clip)
        parsed = json.loads(report)
        self.assertTrue(parsed["errors"])
        self.assertIn("passthrough", " ".join(parsed["notes"]))
        with self.assertRaises(TYPES.SchemaError):
            node.apply(model, "nope", "nope", on_error="raise")

        library = lora_entries({"lora_id": "L", "name": "missing.safetensors", "tags": ["only_tag"]})
        theme = PKG.NODE_CLASS_MAPPINGS["S1Theme"]()
        (result, _report) = theme.decide(
            positive="",
            negative="",
            theme_json=json.dumps(theme_doc(options=[option("only", ["only_tag"])])),
            run="enabled",
            enable_json=TYPES.EMPTY_ENABLE_JSON,
            api_key="",
            api_model="",
        )

        def missing_api():
            return (
                (
                    lambda *_args: (_ for _ in ()).throw(AssertionError("must not patch")),
                    lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not load")),
                    lambda *_args: None,
                ),
                None,
            )

        original = APPLY._import_comfy
        APPLY._import_comfy = missing_api
        try:
            passed_model, passed_clip, passed_report = node.apply(model, library, result, on_error="passthrough")
            self.assertIs(passed_model, model)
            self.assertIsNone(passed_clip)
            self.assertIn("missing.safetensors", json.loads(passed_report)["errors"][0])
            with self.assertRaises(APPLY.ApplyError):
                node.apply(model, library, result, on_error="raise")
        finally:
            APPLY._import_comfy = original

    def test_docs_describe_the_break(self):
        needles = (
            "S1Theme",
            "S1LoraAggregate",
            "S1ThemeCollect",
            "when_upstream",
            "S1ThemeSequence",
            "lora_bindings",
            "disabled",
        )
        for name in ("README.md", "SPEC.md", "MIGRATION.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            for needle in needles:
                self.assertIn(needle, text, f"{name} missing {needle}")
        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        self.assertIn("sidebar", readme)
        self.assertIn("sidebar tab is gone", readme)
        self.assertIn("no apply to node", readme)

    def test_editor_is_modal_only_and_model_checks_pass(self):
        editors = (ROOT / "js" / "s1_editors.js").read_text(encoding="utf-8")
        model_js = (ROOT / "js" / "s1_model.js").read_text(encoding="utf-8")
        combined = (editors + "\n" + model_js).lower()
        self.assertNotIn("registersidebartab", combined)
        self.assertNotIn("sidebar", combined)
        self.assertNotIn("s1 editors", combined)
        self.assertNotIn("apply to node", editors.lower())
        self.assertNotIn("reload from node", editors.lower())
        self.assertIn('name: "SystemOne.LoraRouter.UI"', editors)
        self.assertIn("Open visual editor", editors)
        self.assertIn("const WRITE_DELAY_MS = 220;", editors)
        self.assertIn("const POLL_MS = 500;", editors)
        self.assertIn("s1-invalid", editors)
        self.assertIn("function scheduleLiveWrite(", editors)
        self.assertIn("function liveWrite(", editors)
        self.assertIn("function pollWidgets(", editors)
        self.assertIn("function applyInvalidMarks(", editors)
        self.assertIn("serialize: false", editors)
        self.assertIn('from "../../scripts/api.js"', editors)
        self.assertIn("/object_info/LoraLoader", editors)
        self.assertIn("/object_info/LoraLoaderModelOnly", editors)
        self.assertIn('"/object_info"', editors)
        self.assertIn("/models/loras", editors)
        self.assertIn("Browse loras", editors)
        self.assertIn("Needs a running ComfyUI.", editors)
        self.assertIn("Typed names still work.", editors)
        self.assertIn('readOnlyLine("lora_id"', editors)
        self.assertIn('readOnlyLine("theme_id"', editors)
        self.assertIn('readOnlyLine("option_id"', editors)
        self.assertNotIn('field("lora_id"', editors)
        self.assertNotIn('field("theme_id"', editors)
        self.assertNotIn('field("option_id"', editors)
        self.assertIn('field("upstream theme_id"', editors)
        self.assertIn("strength (model & clip)", editors)
        self.assertIn("input.readOnly = true", editors)
        self.assertLess(editors.index('promptField("positive"'), editors.index('promptField("negative"'))
        self.assertIn("There is no fallback option.", editors)
        self.assertIn("export function assignThemeDocument", model_js)
        self.assertNotIn("export function assignThemeIds", model_js)
        self.assertIn("lora_bindings was removed; selected options contribute tags", model_js)
        self.assertIn("fallback_option_id was removed and is not applied", model_js)
        live = editors[editors.index("function liveWrite(") : editors.index("function pollWidgets(")]
        self.assertLess(
            live.index("commitModel(state.kind, state.model)"),
            live.index('commitModel("enable", state.enable)'),
        )
        self.assertLess(live.index('commitModel("enable", state.enable)'), live.index("writeWidget"))
        self.assertIn("S1LoraLibrary", editors)
        self.assertIn("S1Theme", editors)
        self.assertNotIn("S1ThemeCollect", editors)
        self.assertNotIn("S1LoraAggregate", editors)
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
        completed = subprocess.run(
            [node, "--input-type=module", "--eval", JS_MODEL],
            check=False,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("ok", completed.stdout)

    def test_comfyui_loader_style_import(self):
        script = (
            "import importlib.util, os, sys\n"
            "root = sys.argv[1]\n"
            "name = 's1_loader_check'\n"
            "init = os.path.join(root, '__init__.py')\n"
            "spec = importlib.util.spec_from_file_location(name, init, submodule_search_locations=[root])\n"
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
            "S1LoraAggregate,S1LoraLibrary,S1Theme,S1ThemeCollect",
        )

    def test_top_level_nodes_package_imports(self):
        module = importlib.import_module("nodes")
        self.assertTrue(module.__doc__)


if __name__ == "__main__":
    unittest.main()
