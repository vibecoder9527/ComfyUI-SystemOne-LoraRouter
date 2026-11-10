"""Weighted option tags override LoRA library strengths."""

from __future__ import annotations

import unittest

from tests.harness import (
    AGG,
    TYPES,
    CountingClient,
    as_payload,
    lora_entries,
    option,
    run_theme,
    theme_doc,
)


def _selected(*themes):
    result = None
    for theme_id, option_id, tags in themes:
        result = run_theme(
            theme_json=theme_doc(theme_id=theme_id, options=[option(option_id, tags)]),
            upstream=None if result is None else result.result,
            client=CountingClient(),
        )
    return result


def _aggregate(library, result):
    return AGG.aggregate_loras(
        model=object(),
        clip=None,
        lora_lib=library,
        decision=as_payload(result.result),
    )


class SliderWeightTests(unittest.TestCase):
    def test_weighted_tag_overrides_both_strengths(self):
        library = lora_entries(
            {
                "lora_id": "age_slider",
                "tags": ["age"],
                "strength_model": 0.8,
                "strength_clip": 0.8,
                "slider": True,
            }
        )
        out = _aggregate(library, _selected(("look", "young", ["age:-2"])))
        item = out.report["matched"][0]
        self.assertEqual(item["strength_model"], -2)
        self.assertEqual(item["strength_clip"], -2)
        self.assertEqual(item["matched_tags"], ["age"])
        self.assertEqual(item["sources"], [["look", "young", "age:-2"]])
        self.assertEqual(item["weight_source"]["kind"], "tag")
        self.assertEqual(item["weight_source"]["theme_id"], "look")
        self.assertEqual(item["weight_source"]["option_id"], "young")
        self.assertEqual(item["weight_source"]["tag"], "age:-2")
        self.assertEqual(item["weight_source"]["weight"], -2)
        self.assertEqual(item["slider"], True)
        self.assertEqual(item["warnings"], [])
        self.assertEqual(out.report["skipped"], [])
        self.assertEqual(out.report["warnings"], [])
        self.assertEqual(out.report["applied"][0]["strength_model"], -2)
        self.assertEqual(out.report["applied"][0]["weight_source"]["tag"], "age:-2")

    def test_unweighted_hit_keeps_library_strengths(self):
        library = lora_entries(
            {
                "lora_id": "age_slider",
                "tags": ["age"],
                "strength_model": 0.8,
                "strength_clip": 0.4,
                "slider": True,
            }
        )
        out = _aggregate(library, _selected(("look", "young", ["age"])))
        item = out.report["matched"][0]
        self.assertEqual(item["strength_model"], 0.8)
        self.assertEqual(item["strength_clip"], 0.4)
        self.assertEqual(item["weight_source"], {"kind": "library"})
        self.assertEqual(item["sources"], [["look", "young", "age"]])

    def test_case_insensitive_name_match(self):
        library = lora_entries({"lora_id": "age_slider", "tags": ["Age"], "slider": True, "strength_model": 1, "strength_clip": 1})
        out = _aggregate(library, _selected(("look", "young", ["age:-2"])))
        item = out.report["matched"][0]
        self.assertEqual(item["matched_tags"], ["Age"])
        self.assertEqual(item["strength_model"], -2)

    def test_weight_zero_skips_including_default_on(self):
        library = lora_entries(
            {
                "lora_id": "age_slider",
                "tags": ["age"],
                "enabled_default": True,
                "slider": True,
                "strength_model": 0.8,
                "strength_clip": 0.8,
            }
        )
        out = _aggregate(library, _selected(("look", "young", ["age:0"])))
        self.assertEqual(out.report["matched"], [])
        self.assertEqual(len(out.report["skipped"]), 1)
        skipped = out.report["skipped"][0]
        self.assertEqual(skipped["lora_id"], "age_slider")
        self.assertEqual(skipped["reason"], "weight_0")
        self.assertEqual(skipped["strength_model"], 0)
        self.assertEqual(skipped["weight_source"]["tag"], "age:0")
        self.assertTrue(any("weight 0" in note for note in out.report["notes"]))

    def test_default_on_weighted_hit_uses_the_weight(self):
        library = lora_entries(
            {
                "lora_id": "age_slider",
                "tags": ["age"],
                "enabled_default": True,
                "slider": True,
                "strength_model": 0.8,
                "strength_clip": 0.8,
            }
        )
        out = _aggregate(library, _selected(("look", "young", ["age:+1.5"])))
        item = out.report["matched"][0]
        self.assertEqual(item["strength_model"], 1.5)
        self.assertEqual(item["weight_source"]["requested_weight"], 1.5)

    def test_max_abs_and_theme_order_tie_break(self):
        library = lora_entries({"lora_id": "age_slider", "tags": ["age"], "slider": True, "strength_model": 1, "strength_clip": 1})
        # -3 has the greater absolute value.
        out = _aggregate(
            library,
            _selected(("first", "a", ["age:1"]), ("second", "b", ["age:-3"])),
        )
        item = out.report["matched"][0]
        self.assertEqual(item["strength_model"], -3)
        self.assertEqual(item["weight_source"]["theme_id"], "second")
        self.assertEqual(item["weight_source"]["tag"], "age:-3")
        self.assertEqual(
            item["sources"],
            [["first", "a", "age:1"], ["second", "b", "age:-3"]],
        )

        # Equal absolute value: first theme in decision order wins.
        tied = _aggregate(
            library,
            _selected(("first", "a", ["age:2"]), ("second", "b", ["age:-2"])),
        )
        item = tied.report["matched"][0]
        self.assertEqual(item["strength_model"], 2)
        self.assertEqual(item["weight_source"]["theme_id"], "first")
        self.assertEqual(item["weight_source"]["tag"], "age:2")

    def test_clamp_out_of_range(self):
        library = lora_entries({"lora_id": "age_slider", "tags": ["age"], "slider": True, "strength_model": 1, "strength_clip": 1})
        out = _aggregate(library, _selected(("look", "young", ["age:8"])))
        item = out.report["matched"][0]
        self.assertEqual(item["strength_model"], 5)
        self.assertTrue(any("clamped" in warning for warning in item["warnings"]))
        self.assertEqual(out.report["warnings"], item["warnings"])
        self.assertEqual(item["weight_source"]["requested_weight"], 8)
        self.assertEqual(item["weight_source"]["weight"], 5)

    def test_non_slider_negative_applies_with_warning(self):
        library = lora_entries(
            {
                "lora_id": "style",
                "tags": ["age"],
                "slider": False,
                "strength_model": 0.8,
                "strength_clip": 0.8,
            }
        )
        out = _aggregate(library, _selected(("look", "young", ["age:-2"])))
        item = out.report["matched"][0]
        self.assertEqual(item["strength_model"], -2)
        self.assertFalse(item["slider"])
        self.assertTrue(any("non-slider" in warning for warning in item["warnings"]))
        self.assertEqual(out.report["warnings"], item["warnings"])

    def test_library_json_strips_weighted_library_tags_and_defaults_slider(self):
        library = TYPES.parse_lora_library(
            {
                "loras": [
                    {
                        "lora_id": "age_slider",
                        "name": "age.safetensors",
                        "strength_model": 0.8,
                        "strength_clip": 0.8,
                        "tags": ["age:-2", "Age"],
                    }
                ]
            }
        )
        entry = library.loras["age_slider"]
        self.assertFalse(entry.slider)
        self.assertEqual(entry.tags, ["age", "Age"])


if __name__ == "__main__":
    unittest.main()
