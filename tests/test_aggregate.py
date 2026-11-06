"""Tag matching, dedupe, collect, and apply_loras."""

from __future__ import annotations

import importlib
import unittest

from tests.harness import (
    AGG,
    APPLY,
    PACKAGE_NAME,
    TYPES,
    CountingClient,
    FixedChoiceClient,
    ScoreClient,
    as_payload,
    lora_entries,
    option,
    read_example,
    run_theme,
    theme_doc,
)

BLOCKER = importlib.import_module(PACKAGE_NAME + ".schema.blocker")


def _chain(choice="anime", scores=None):
    """Art-style root, then the character theme only when anime was selected.

    That is the option-slot wire: the character node is not called for any
    other slot.
    """

    root = run_theme(
        theme_json=read_example("theme.art_style.json"),
        client=FixedChoiceClient(choice),
    )
    if choice != "anime":
        return root
    return run_theme(
        theme_json=read_example("theme.character_pack.json"),
        upstream=root.result,
        client=ScoreClient({"waifu_a": 1, "waifu_b": 1} if scores is None else scores),
    )


class AggregateTests(unittest.TestCase):
    def test_example_chain_dedupes_and_uses_library_strength(self):
        library = TYPES.parse_lora_library(read_example("lora_library.minimal.json"))
        result = _chain().result
        self.assertEqual(result.tags, ["style_anime", "char_a", "char_b"])
        model = object()
        clip = object()
        outcome = AGG.aggregate_loras(
            model=model,
            clip=clip,
            lora_lib=library,
            decision=as_payload(result),
        )
        self.assertIs(outcome.model, model)
        self.assertIs(outcome.clip, clip)
        applied_ids = [item["lora_id"] for item in outcome.report["applied"]]
        self.assertEqual(applied_ids, ["char_a", "style_anime_v3"])
        by_id = {item["lora_id"]: item for item in outcome.report["matched"]}
        self.assertEqual(by_id["style_anime_v3"]["strength_model"], 0.8)
        self.assertEqual(by_id["style_anime_v3"]["strength_clip"], 0.8)
        self.assertEqual(by_id["style_anime_v3"]["sources"], [["art_style", "anime", "style_anime"]])
        self.assertEqual(by_id["char_a"]["strength_model"], 0.9)
        self.assertEqual(by_id["char_a"]["strength_clip"], 0.9)
        self.assertEqual(by_id["char_a"]["sources"], [["character_pack", "waifu_a", "char_a"]])
        self.assertFalse(outcome.report["applied"][0]["loaded"])
        self.assertTrue(any("ComfyUI APIs unavailable" in note for note in outcome.report["notes"]))
        self.assertNotIn("char_b", applied_ids)
        self.assertEqual(outcome.report["skipped"], [])

    def test_none_and_realistic_and_disabled_library_entry(self):
        library = TYPES.parse_lora_library(read_example("lora_library.minimal.json"))
        extra = {
            "lora_id": "should_not",
            "name": "should_not.safetensors",
            "strength_model": 1,
            "strength_clip": 1,
            "tags": ["should_not_apply"],
        }
        raw = {
            "version": 1,
            "loras": [
                {
                    "lora_id": entry.lora_id,
                    "name": entry.name,
                    "strength_model": entry.strength_model,
                    "strength_clip": entry.strength_clip,
                    "tags": list(entry.tags),
                }
                for entry in library.loras.values()
            ]
            + [extra],
        }
        library = TYPES.parse_lora_library(raw)
        none = run_theme(
            theme_json=read_example("theme.art_style.json"),
            client=FixedChoiceClient("none"),
        )
        none_out = AGG.aggregate_loras(model=object(), clip=None, lora_lib=library, decision=as_payload(none.result))
        self.assertEqual(none_out.report["matched"], [])
        self.assertEqual(none_out.report["applied"], [])
        self.assertIsNone(none_out.clip)
        self.assertTrue(any("No LoRAs were selected" in note for note in none_out.report["notes"]))

        real = _chain("realistic", scores={"waifu_a": 1, "waifu_b": 1})
        real_out = AGG.aggregate_loras(model=object(), clip=None, lora_lib=library, decision=as_payload(real.result))
        self.assertEqual([item["lora_id"] for item in real_out.report["matched"]], ["style_realistic"])
        self.assertEqual(real_out.report["matched"][0]["strength_model"], 0.7)

        disabled = TYPES.parse_lora_library(
            {
                "loras": [
                    {
                        "lora_id": "style_anime_v3",
                        "name": "anime_style_v3.safetensors",
                        "strength_model": 0.8,
                        "strength_clip": 0.8,
                        "tags": ["style_anime"],
                        "enabled_default": False,
                    },
                    {
                        "lora_id": "char_a",
                        "name": "character_a.safetensors",
                        "strength_model": 0.9,
                        "strength_clip": 0.9,
                        "tags": ["char_a"],
                    },
                ]
            }
        )
        out = AGG.aggregate_loras(
            model=object(),
            clip=None,
            lora_lib=disabled,
            decision=as_payload(_chain().result),
        )
        self.assertEqual([item["lora_id"] for item in out.report["matched"]], ["char_a"])
        self.assertEqual(out.report["skipped"], [{"lora_id": "style_anime_v3", "reason": "enabled_default is false"}])

    def test_dedupe_case_and_stored_strengths(self):
        first = run_theme(
            theme_json=theme_doc(theme_id="a", options=[option("one", ["style_anime"])]),
            client=CountingClient(),
        )
        second = run_theme(
            theme_json=theme_doc(theme_id="b", options=[option("two", ["style_anime", "Style_anime"])]),
            upstream=first.result,
            client=CountingClient(),
        )
        library = lora_entries(
            {
                "lora_id": "z_style",
                "tags": ["style_anime", "Style_anime"],
                "strength_model": 0.85,
                "strength_clip": 0.4,
            },
            {"lora_id": "a_other", "tags": ["missing"]},
        )
        out = AGG.aggregate_loras(model=object(), clip=None, lora_lib=library, decision=as_payload(second.result))
        self.assertEqual([item["lora_id"] for item in out.report["matched"]], ["z_style"])
        matched = out.report["matched"][0]
        self.assertEqual(matched["strength_model"], 0.85)
        self.assertEqual(matched["strength_clip"], 0.4)
        self.assertEqual(matched["matched_tags"], ["style_anime", "Style_anime"])
        self.assertEqual(
            matched["sources"],
            [
                ["a", "one", "style_anime"],
                ["b", "two", "style_anime"],
                ["b", "two", "Style_anime"],
            ],
        )
        self.assertEqual(out.report["skipped"], [])

    def test_collect_is_disjoint_and_conflicting_theme_raises(self):
        left = run_theme(
            theme_json=theme_doc(theme_id="left", options=[option("a", ["ta"])]),
            client=CountingClient(),
        ).result
        right = run_theme(
            theme_json=theme_doc(theme_id="right", options=[option("b", ["ta", "tb"])]),
            client=CountingClient(),
        ).result
        merged = AGG.collect_theme_results(left, right)
        self.assertEqual([item.theme_id for item in merged.decisions], ["left", "right"])
        self.assertEqual(merged.tags, ["ta", "tb"])
        shared = run_theme(
            theme_json=theme_doc(theme_id="left", options=[option("c", ["tc"])]),
            client=CountingClient(),
        ).result
        with self.assertRaises(TYPES.SchemaError) as ctx:
            AGG.collect_theme_results(left, shared)
        self.assertIn("left", str(ctx.exception))
        self.assertIn("conflicting", str(ctx.exception))
        with self.assertRaises(TYPES.SchemaError):
            AGG.collect_theme_results(left, object())

    def test_collect_merges_a_shared_ancestor_once(self):
        parent = run_theme(
            theme_json=theme_doc(theme_id="parent", options=[option("a", ["ta"])]),
            client=CountingClient(),
        ).result
        left = run_theme(
            theme_json=theme_doc(theme_id="left", options=[option("b", ["tb"])]),
            upstream=parent,
            client=CountingClient(),
        ).result
        right = run_theme(
            theme_json=theme_doc(theme_id="right", options=[option("c", ["tc"])]),
            upstream=parent,
            client=CountingClient(),
        ).result
        left.errors.append("shared")
        right.errors.append("shared")
        right.errors.append("only-right")
        merged = AGG.collect_theme_results(left, right)
        self.assertEqual([item.theme_id for item in merged.decisions], ["parent", "left", "right"])
        self.assertEqual(merged.tags, ["ta", "tb", "tc"])
        self.assertEqual(merged.tags.count("ta"), 1)
        self.assertEqual(merged.errors, ["shared", "only-right"])
        swapped = AGG.collect_theme_results(right, left)
        self.assertEqual([item.theme_id for item in swapped.decisions], ["parent", "right", "left"])
        self.assertEqual([item.theme_id for item in left.decisions], ["parent", "left"])
        same = AGG.collect_theme_results(parent, parent)
        self.assertEqual([item.theme_id for item in same.decisions], ["parent"])
        self.assertEqual(same.tags, ["ta"])

        def decision(theme_id, selected, tags, option_tags, raw=None):
            return TYPES.ThemeDecision(
                theme_id=theme_id,
                status="ok",
                enabled=True,
                selected=list(selected),
                tags=list(tags),
                select_mode="single",
                option_tags=list(option_tags),
                raw=raw,
                reason="ran",
            )

        base = TYPES.build_theme_result([decision("p", ["a"], ["ta"], [("a", ["ta"])], {"choice": "a"})])
        other_tags = TYPES.build_theme_result(
            [decision("p", ["a"], ["ta"], [("a", ["other"])], {"choice": "a"})]
        )
        with self.assertRaises(TYPES.SchemaError) as tags_ctx:
            AGG.collect_theme_results(base, other_tags)
        self.assertIn("p", str(tags_ctx.exception))
        other_raw = TYPES.build_theme_result(
            [decision("p", ["a"], ["ta"], [("a", ["ta"])], {"choice": "a", "extra": 1})]
        )
        with self.assertRaises(TYPES.SchemaError):
            AGG.collect_theme_results(base, other_raw)

    def test_collect_passthrough_ignores_blocker_and_requires_one_payload(self):
        left = run_theme(
            theme_json=theme_doc(theme_id="left", options=[option("a", ["ta"])]),
            client=CountingClient(),
        ).result
        right = run_theme(
            theme_json=theme_doc(theme_id="right", options=[option("b", ["tb"])]),
            client=CountingClient(),
        ).result
        payload_a = as_payload(left, slot_option_id="a")
        payload_b = as_payload(right, slot_option_id="b")
        self.assertIs(AGG.collect_decisions(payload_a, None), payload_a)
        self.assertIs(AGG.collect_decisions(None, payload_b), payload_b)
        self.assertIs(AGG.collect_decisions(payload_a, BLOCKER.execution_blocker(None)), payload_a)
        self.assertIs(AGG.collect_decisions(BLOCKER.execution_blocker("skip"), payload_b), payload_b)
        merged = AGG.collect_decisions(payload_a, payload_b)
        self.assertEqual(merged.emitted_reason, "collected")
        self.assertEqual([item.theme_id for item in merged.result.decisions], ["left", "right"])
        with self.assertRaises(TYPES.SchemaError) as empty:
            AGG.collect_decisions(None, None)
        self.assertIn("a or b", str(empty.exception))
        with self.assertRaises(TYPES.SchemaError):
            AGG.collect_decisions(BLOCKER.execution_blocker(None), BLOCKER.execution_blocker(None))
        with self.assertRaises(TYPES.SchemaError):
            AGG.collect_decisions(payload_a, object())

    def test_collect_runs_when_one_option_is_wired(self):
        """One selected option is enough. The other socket can be omitted.

        An ExecutionBlocker on the sibling does not have to be connected.
        That is Theme option slot → Theme Collect a/b with a single wire.
        """

        wired = run_theme(
            theme_json=theme_doc(theme_id="wired", options=[option("a", ["ta"])]),
            client=CountingClient(),
        ).result
        payload = as_payload(wired, slot_option_id="a")
        self.assertIs(AGG.collect_decisions(payload), payload)
        self.assertIs(AGG.collect_decisions(payload, None), payload)
        self.assertEqual(AGG.collect_decisions(payload).slot_option_id, "a")

    def test_theme_errors_do_not_cancel_kept_tags(self):
        upstream = run_theme(
            theme_json=read_example("theme.art_style.json"),
            client=FixedChoiceClient("anime"),
        ).result
        failed = run_theme(
            theme_json=theme_doc(theme_id="boom", options=[option("a", ["other"]), option("b")]),
            upstream=upstream,
            on_error="passthrough",
            client=FixedChoiceClient("nope"),
        ).result
        library = TYPES.parse_lora_library(read_example("lora_library.minimal.json"))
        out = AGG.aggregate_loras(model=object(), clip=None, lora_lib=library, decision=as_payload(failed))
        self.assertEqual([item["lora_id"] for item in out.report["matched"]], ["style_anime_v3"])
        self.assertTrue(out.report["errors"])
        self.assertTrue(any("already recorded theme errors" in note for note in out.report["notes"]))

    def test_bad_wire_and_missing_file_follow_on_error(self):
        model = object()
        clip = object()
        with self.assertRaises(TYPES.SchemaError):
            AGG.aggregate_loras(model=model, clip=clip, lora_lib=object(), decision=object(), on_error="raise")
        library = lora_entries({"lora_id": "L", "name": "missing.safetensors", "tags": ["only_tag"]})
        result = run_theme(
            theme_json=theme_doc(options=[option("only", ["only_tag"])]),
            client=CountingClient(),
        ).result

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
            passed = AGG.aggregate_loras(
                model=model, clip=None, lora_lib=library, decision=as_payload(result), on_error="passthrough",
            )
            self.assertIs(passed.model, model)
            self.assertFalse(passed.report["applied"][0]["loaded"])
            self.assertIn("missing.safetensors", passed.report["errors"][0])
            with self.assertRaises(APPLY.ApplyError):
                AGG.aggregate_loras(
                    model=model, clip=None, lora_lib=library, decision=as_payload(result), on_error="raise",
                )
        finally:
            APPLY._import_comfy = original

    def test_comfy_hook_patches_once_and_keeps_clip_none(self):
        library = lora_entries(
            {"lora_id": "b_lora", "name": "b.safetensors", "tags": ["tb"], "strength_model": 0.2, "strength_clip": 0.3},
            {"lora_id": "a_lora", "name": "a.safetensors", "tags": ["ta"], "strength_model": 0.4, "strength_clip": 0.6},
        )
        result = run_theme(
            theme_json=theme_doc(
                select_mode="multi",
                options=[option("b", ["tb"]), option("a", ["ta"])],
            ),
            client=ScoreClient({"a": 1, "b": 1}),
        ).result
        new_models = [object(), object()]
        seen = []

        def present_api():
            def get_full_path(_kind, name):
                return f"/loras/{name}"

            def load_torch_file(path, safe_load=True):
                seen.append(("torch", path, safe_load))
                return {"path": path}

            def load_lora_for_models(model, clip, lora_object, strength_model, strength_clip):
                seen.append(("apply", model, clip, lora_object, strength_model, strength_clip))
                return (new_models[len([item for item in seen if item[0] == "apply"]) - 1], object())

            return (load_lora_for_models, load_torch_file, get_full_path), None

        original = APPLY._import_comfy
        APPLY._import_comfy = present_api
        model = object()
        try:
            outcome = AGG.aggregate_loras(model=model, clip=None, lora_lib=library, decision=as_payload(result))
        finally:
            APPLY._import_comfy = original
        self.assertIs(outcome.model, new_models[1])
        self.assertIsNone(outcome.clip)
        self.assertEqual([item["lora_id"] for item in outcome.report["applied"]], ["a_lora", "b_lora"])
        self.assertTrue(all(item["loaded"] for item in outcome.report["applied"]))
        applies = [item for item in seen if item[0] == "apply"]
        self.assertEqual(applies[0][4:], (0.4, 0.6))
        self.assertIs(applies[0][1], model)
        self.assertIsNone(applies[0][2])
        self.assertEqual(applies[1][4:], (0.2, 0.3))
        self.assertIs(applies[1][1], new_models[0])
        self.assertTrue(any("Patched 2 LoRA" in note for note in outcome.report["notes"]))


if __name__ == "__main__":
    unittest.main()
