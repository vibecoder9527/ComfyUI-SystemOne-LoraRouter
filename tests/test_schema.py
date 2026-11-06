"""Schema, id helpers, and removed-field checks."""

from __future__ import annotations

import json
import unittest

from tests.harness import IDS, ROOT, THEME_IDS, TYPES, option, read_example, theme_doc


class SchemaTests(unittest.TestCase):
    def test_empty_defaults_and_examples_parse(self):
        library = TYPES.parse_lora_library(TYPES.EMPTY_LORA_LIBRARY_JSON)
        self.assertEqual(library.loras, {})
        theme = TYPES.parse_theme(TYPES.EMPTY_THEME_JSON)
        self.assertEqual(theme.theme_id, "theme_1")
        self.assertEqual(theme.options, [])
        rules = TYPES.parse_enable_rules(TYPES.EMPTY_ENABLE_JSON)
        self.assertEqual(rules.match, "any")
        self.assertEqual(rules.clauses, [])

        parsed = TYPES.parse_lora_library(read_example("lora_library.minimal.json"))
        self.assertEqual(
            parsed.get("style_anime_v3").tags,
            ["style_anime"],
        )
        self.assertEqual(parsed.get("style_anime_v3").strength_model, 0.8)
        self.assertEqual(parsed.get("style_anime_v3").strength_clip, 0.8)
        self.assertEqual(parsed.get("char_a").strength_model, 0.9)
        art = TYPES.parse_theme(read_example("theme.art_style.json"))
        self.assertEqual(art.none_option_id, "none")
        self.assertEqual(
            [item.option_id for item in art.options],
            ["anime", "realistic", "none"],
        )
        self.assertEqual(art.options[2].tags, ["should_not_apply"])
        pack = TYPES.parse_theme(read_example("theme.character_pack.json"))
        self.assertEqual(pack.select_mode, "multi")
        self.assertEqual(pack.options[0].tags, ["char_a"])
        self.assertEqual(pack.options[1].tags, ["char_b"])
        TYPES.parse_theme(read_example("theme.empty.json"))
        TYPES.parse_enable_rules(read_example("enable.empty.json"))
        anime = TYPES.parse_enable_rules(read_example("enable.when_anime.json"))
        self.assertEqual(anime.clauses[0].theme_id, "art_style")
        self.assertEqual(anime.clauses[0].op, "includes_any")
        self.assertEqual(anime.clauses[0].option_ids, ["anime"])
        self.assertTrue((ROOT / "examples" / "legacy" / "theme_library.minimal.json").is_file())
        self.assertFalse((ROOT / "examples" / "theme_library.minimal.json").exists())
        self.assertFalse((ROOT / "examples" / "sequence.minimal.json").exists())

    def test_removed_fields_and_one_theme(self):
        with self.assertRaises(TYPES.SchemaError) as ctx:
            TYPES.parse_theme(theme_doc(fallback_option_id="a", options=[option("a")]))
        self.assertIn("fallback_option_id was removed and is not applied", str(ctx.exception))
        with self.assertRaises(TYPES.SchemaError) as ctx:
            TYPES.parse_theme(
                {
                    "version": 1,
                    "themes": [theme_doc()],
                }
            )
        self.assertIn("a theme node stores one theme", str(ctx.exception))
        with self.assertRaises(TYPES.SchemaError) as ctx:
            TYPES.parse_theme(
                theme_doc(
                    options=[
                        {
                            "option_id": "a",
                            "label": "a",
                            "description": "a",
                            "lora_bindings": [{"lora_id": "style_anime_v3"}],
                        }
                    ]
                )
            )
        self.assertIn("lora_bindings was removed", str(ctx.exception))
        kept = TYPES.parse_theme(
            theme_doc(
                theme_id="art_style",
                select_mode="single",
                none_option_id="none",
                options=[option("none", ["should_not_apply"]), option("anime", ["style_anime"])],
            )
        )
        self.assertEqual(kept.none_option_id, "none")
        with self.assertRaises(TYPES.SchemaError) as ctx:
            TYPES.parse_theme(theme_doc(none_option_id="missing", options=[option("a")]))
        self.assertIn("none_option_id", str(ctx.exception))

    def test_rejects_bad_documents(self):
        with self.assertRaises(TYPES.SchemaError):
            TYPES.parse_lora_library("{")
        with self.assertRaises(TYPES.SchemaError):
            TYPES.parse_lora_library(
                {"loras": [{"name": "a.safetensors", "strength_model": 1, "strength_clip": 1}]}
            )
        with self.assertRaises(TYPES.SchemaError):
            TYPES.parse_lora_library(
                {"loras": [{"lora_id": "a", "name": "a.safetensors", "strength_model": 1}]}
            )
        with self.assertRaises(TYPES.SchemaError):
            TYPES.parse_lora_library(
                {
                    "loras": [
                        {
                            "lora_id": "a",
                            "name": "a.safetensors",
                            "strength_model": True,
                            "strength_clip": 1,
                        }
                    ]
                }
            )
        with self.assertRaises(TYPES.SchemaError):
            TYPES.parse_theme(theme_doc(theme_id="has space", options=[]))
        with self.assertRaises(TYPES.SchemaError):
            TYPES.parse_theme({"title": "T", "instructions": "I", "select_mode": "single", "options": []})
        with self.assertRaises(TYPES.SchemaError):
            TYPES.parse_theme(
                theme_doc(options=[{"label": "L", "description": "D"}])
            )
        with self.assertRaises(TYPES.SchemaError) as ctx:
            TYPES.parse_theme(theme_doc(version=2, options=[]))
        self.assertIn("version", str(ctx.exception))
        with self.assertRaises(TYPES.SchemaError):
            TYPES.parse_theme(theme_doc(options=[option("a"), option("a")]))
        differing = TYPES.parse_lora_library(
            {
                "loras": [
                    {
                        "lora_id": "style_anime_v3",
                        "name": "a.safetensors",
                        "strength_model": 0.85,
                        "strength_clip": 0.4,
                    }
                ]
            }
        )
        entry = differing.get("style_anime_v3")
        self.assertEqual(entry.strength_model, 0.85)
        self.assertEqual(entry.strength_clip, 0.4)
        empty_ok = TYPES.parse_theme(theme_doc(options=[]))
        self.assertEqual(empty_ok.options, [])

    def test_enable_rules(self):
        rules = TYPES.parse_enable_rules({"clauses": []})
        self.assertEqual(rules.match, "any")
        self.assertEqual(rules.clauses, [])
        with self.assertRaises(TYPES.SchemaError):
            TYPES.parse_enable_rules(
                {"clauses": [{"theme_id": "art_style", "op": "eq", "option_ids": ["a", "b"]}]}
            )
        with self.assertRaises(TYPES.SchemaError):
            TYPES.parse_enable_rules(
                {"clauses": [{"theme_id": "art_style", "op": "skipped", "option_ids": ["a"]}]}
            )
        bare = TYPES.parse_enable_rules(
            {"match": "all", "clauses": [{"theme_id": "art_style", "op": "answered"}]}
        )
        self.assertEqual(bare.match, "all")
        self.assertEqual(bare.clauses[0].option_ids, [])
        with self.assertRaises(TYPES.SchemaError):
            TYPES.parse_enable_rules(
                {"clauses": [{"theme_id": "art_style", "op": "includes_any", "option_ids": []}]}
            )

    def test_result_tags_and_duplicate_theme_id(self):
        ok = TYPES.ThemeDecision(
            theme_id="a",
            status="ok",
            enabled=True,
            selected=["anime"],
            tags=["b", "a"],
            select_mode="single",
        )
        skipped = TYPES.ThemeDecision(
            theme_id="b",
            status="skipped",
            enabled=False,
            selected=[],
            tags=["nope"],
            select_mode="single",
            reason="disabled",
        )
        later = TYPES.ThemeDecision(
            theme_id="c",
            status="ok",
            enabled=True,
            selected=["x"],
            tags=["a", "c"],
            select_mode="single",
        )
        result = TYPES.build_theme_result([ok, skipped, later])
        self.assertEqual(result.tags, ["b", "a", "c"])
        self.assertEqual(result.get("b").status, "skipped")
        public = TYPES.public_decision(ok)
        self.assertNotIn("option_tags", public)
        with self.assertRaises(TYPES.SchemaError):
            TYPES.build_theme_result([ok, ok])


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
        minimal = json.loads(read_example("lora_library.minimal.json"))
        ensured = IDS.ensure_lora_ids(minimal["loras"])
        self.assertEqual(
            [entry["lora_id"] for entry in ensured],
            ["style_anime_v3", "style_realistic", "char_a"],
        )

    def test_shared_strength_writes_both_fields_and_drops_strength_key(self):
        fields = IDS.shared_strength_fields(0.8)
        self.assertEqual(fields, {"strength_model": 0.8, "strength_clip": 0.8})
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
        self.assertEqual(out["strength_model"], 0.8)
        self.assertEqual(out["strength_clip"], 0.8)
        self.assertNotIn("strength", out)
        with self.assertRaises(TypeError):
            IDS.shared_strength_fields(True)
        with self.assertRaises(ValueError):
            IDS.shared_strength_fields(float("inf"))


class ThemeIdHelperTests(unittest.TestCase):
    def test_next_ids_fill_gaps(self):
        self.assertEqual(THEME_IDS.next_theme_id([]), "theme_1")
        self.assertEqual(THEME_IDS.next_theme_id(["theme_1", "theme_3"]), "theme_2")
        self.assertEqual(THEME_IDS.next_theme_id(["art_style"]), "theme_1")
        self.assertEqual(THEME_IDS.next_option_id(["option_1", "option_3"]), "option_2")
        self.assertEqual(THEME_IDS.next_option_id(["anime", "option_2"]), "option_1")

    def test_ensure_keeps_manual_ids_and_scopes_options(self):
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
            {"theme_id": "theme_1", "options": [{"option_id": "   "}, {"option_id": "waifu_a"}]},
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
            [item["option_id"] for item in filled[0]["options"]],
            ["anime", "option_2", "option_1"],
        )
        self.assertEqual(
            [item["option_id"] for item in filled[1]["options"]],
            ["option_1", "waifu_a"],
        )
        self.assertNotIn("options", filled[2])
        self.assertEqual(original[0]["theme_id"], "")
        self.assertIsNot(filled[0]["options"][0], original[0]["options"][0])
        legacy = json.loads((ROOT / "examples" / "legacy" / "theme_library.minimal.json").read_text(encoding="utf-8"))
        ensured = THEME_IDS.ensure_theme_ids(legacy["themes"])
        self.assertEqual([theme["theme_id"] for theme in ensured], ["art_style", "character_pack"])
        one = THEME_IDS.ensure_theme_document({"title": "T", "options": [{"label": "L"}]})
        self.assertEqual(one["theme_id"], "theme_1")
        self.assertEqual(one["options"][0]["option_id"], "option_1")
        self.assertNotIn("theme_id", {"title": "T"})

    def test_option_ids_do_not_leak_across_lists(self):
        first = THEME_IDS.ensure_option_ids([{"option_id": ""}, {"option_id": "anime"}])
        second = THEME_IDS.ensure_option_ids([{"option_id": ""}, {"option_id": "anime"}])
        self.assertEqual([item["option_id"] for item in first], ["option_1", "anime"])
        self.assertEqual([item["option_id"] for item in second], ["option_1", "anime"])


if __name__ == "__main__":
    unittest.main()
