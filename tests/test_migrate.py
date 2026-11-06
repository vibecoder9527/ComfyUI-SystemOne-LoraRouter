"""Offline migration. These helpers do not register nodes or call SystemOne."""

from __future__ import annotations

import json
import unittest

from tests.harness import MIGRATE, ROOT, TYPES, read_example


def _legacy(name: str):
    return (ROOT / "examples" / "legacy" / name).read_text(encoding="utf-8")


class MigrateTests(unittest.TestCase):
    def test_library_bindings_become_tags_and_strengths_are_dropped(self):
        migrated = MIGRATE.migrate_theme_library(_legacy("theme_library.minimal.json"))
        self.assertEqual(len(migrated), 2)
        art, pack = migrated
        self.assertEqual(art.document["theme_id"], "art_style")
        anime = art.document["options"][0]
        self.assertEqual(anime["tags"], ["style_anime_v3"])
        self.assertNotIn("lora_bindings", anime)
        self.assertTrue(any("style_anime_v3" in note for note in art.notes))
        self.assertTrue(any("strength" in note for note in art.notes))
        realistic = art.document["options"][1]
        self.assertEqual(realistic["tags"], ["style_realistic"])
        self.assertNotIn("strength", " ".join(note for note in art.notes if "realistic" in note or "options[1]" in note))
        TYPES.parse_theme(art.document)
        waifu_a = pack.document["options"][0]
        self.assertEqual(waifu_a["tags"], ["char_a"])
        self.assertNotIn("lora_bindings", waifu_a)
        self.assertTrue(any("strength" in note for note in pack.notes))
        waifu_b = pack.document["options"][1]
        self.assertNotIn("tags", waifu_b)
        TYPES.parse_theme(pack.document)
        self.assertEqual(pack.document["select_mode"], "multi")
        with self.assertRaises(TYPES.SchemaError):
            TYPES.parse_theme(json.loads(_legacy("theme_library.minimal.json")))

    def test_existing_tags_win_and_fallback_is_not_applied(self):
        source = {
            "theme_id": "art_style",
            "title": "Style",
            "instructions": "Pick.",
            "select_mode": "single",
            "fallback_option_id": "anime",
            "options": [
                {
                    "option_id": "anime",
                    "label": "Anime",
                    "description": "A",
                    "tags": ["style_anime"],
                    "lora_bindings": [
                        {"lora_id": "style_anime_v3", "strength_model": 0.85, "strength_clip": 0.2}
                    ],
                }
            ],
        }
        migrated = MIGRATE.migrate_theme_document(source)
        self.assertEqual(migrated.document["options"][0]["tags"], ["style_anime"])
        self.assertNotIn("lora_bindings", migrated.document["options"][0])
        self.assertNotIn("fallback_option_id", migrated.document)
        self.assertTrue(any("fallback_option_id" in note and "not applied" in note for note in migrated.notes))
        self.assertTrue(any("dropped lora_bindings" in note for note in migrated.notes))
        self.assertTrue(any("strength" in note for note in migrated.notes))
        parsed = TYPES.parse_theme(migrated.document)
        self.assertEqual(parsed.options[0].tags, ["style_anime"])
        self.assertIsNone(parsed.none_option_id)

    def test_blank_ids_are_filled_and_manual_ids_stay(self):
        migrated = MIGRATE.migrate_theme_document(
            {
                "title": "T",
                "instructions": "I",
                "select_mode": "single",
                "options": [
                    {
                        "label": "L",
                        "description": "D",
                        "lora_bindings": [{"lora_id": "char_a"}, {"lora_id": "char_a"}],
                    }
                ],
            }
        )
        self.assertEqual(migrated.document["theme_id"], "theme_1")
        self.assertEqual(migrated.document["options"][0]["option_id"], "option_1")
        self.assertEqual(migrated.document["options"][0]["tags"], ["char_a"])
        TYPES.parse_theme(migrated.document)
        with self.assertRaises(TYPES.SchemaError):
            MIGRATE.migrate_theme_document(_legacy("theme_library.minimal.json"))

    def test_retag_appends_lora_id_tags_without_rewriting_strength(self):
        library = json.loads(read_example("lora_library.minimal.json"))
        themes = [
            item.document
            for item in MIGRATE.migrate_theme_library(_legacy("theme_library.minimal.json"))
        ]
        updated, notes = MIGRATE.retag_lora_library(library, themes)
        by_id = {entry["lora_id"]: entry for entry in updated["loras"]}
        self.assertEqual(by_id["style_anime_v3"]["strength_model"], 0.8)
        self.assertEqual(by_id["style_anime_v3"]["strength_clip"], 0.8)
        self.assertEqual(by_id["style_anime_v3"]["tags"], ["style_anime", "style_anime_v3"])
        self.assertEqual(by_id["char_a"]["tags"], ["char_a"])
        self.assertTrue(any("style_anime_v3" in note for note in notes))
        self.assertFalse(any(note.startswith("added tag 'char_a'") for note in notes))
        again, second_notes = MIGRATE.retag_lora_library(updated, themes)
        self.assertEqual(
            [entry["tags"] for entry in again["loras"]],
            [entry["tags"] for entry in updated["loras"]],
        )
        self.assertFalse(any(note.startswith("added tag") for note in second_notes))
        descriptive, unused_notes = MIGRATE.retag_lora_library(
            library,
            [json.loads(read_example("theme.art_style.json"))],
        )
        self.assertEqual(descriptive["loras"][0]["tags"], ["style_anime"])
        self.assertTrue(any("style_anime" in note and "does not match" in note for note in unused_notes))
        self.assertTrue(any("should_not_apply" in note for note in unused_notes))

    def test_sequence_plan_maps_theme_ids_and_warns_about_rewrites(self):
        plan = MIGRATE.plan_sequence(_legacy("sequence.minimal.json"))
        self.assertEqual(
            plan["removed"],
            [
                "S1ThemeLibrary",
                "S1ThemeSequence",
                "lora_bindings",
                "fallback_option_id",
                "strength_conflict",
                "sequence_json",
            ],
        )
        root, child = plan["nodes"]
        self.assertEqual(root["step_id"], "s1")
        self.assertEqual(root["theme_id"], "art_style")
        self.assertEqual(root["run"], "enabled")
        self.assertEqual(root["enable_json"]["clauses"], [])
        self.assertEqual(child["run"], "when_upstream")
        self.assertEqual(child["theme_id"], "character_pack")
        clause = child["enable_json"]["clauses"][0]
        self.assertEqual(clause["theme_id"], "art_style")
        self.assertNotEqual(clause["theme_id"], "s1")
        self.assertEqual(clause["op"], "includes_any")
        self.assertEqual(clause["option_ids"], ["anime"])
        self.assertTrue(any("rewrite_options" in note for note in child["warnings"]))
        self.assertTrue(any("rewrite_instructions" in note for note in child["warnings"]))
        TYPES.parse_enable_rules(child["enable_json"])
        dup = MIGRATE.plan_sequence(
            {
                "steps": [
                    {"step_id": "s1", "theme_id": "same", "enabled_by_default": True},
                    {"step_id": "s2", "theme_id": "same", "enabled_by_default": False},
                ]
            }
        )
        self.assertEqual(dup["nodes"][1]["run"], "disabled")
        self.assertTrue(any("unique theme ids" in note for note in dup["warnings"]))
        disabled = MIGRATE.plan_sequence(
            {
                "steps": [
                    {
                        "step_id": "s1",
                        "theme_id": "gate",
                        "enabled_by_default": True,
                        "dependencies": [
                            {
                                "when": {"step_id": "s1", "op": "answered"},
                                "actions": [{"type": "disable_step"}],
                            }
                        ],
                    }
                ]
            }
        )
        self.assertEqual(disabled["nodes"][0]["run"], "disabled")
        self.assertTrue(any("disable_step" in note for note in disabled["nodes"][0]["warnings"]))


if __name__ == "__main__":
    unittest.main()
