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
        for name in ("run", "enable_json", "theme_result", "S1_THEME_RESULT", "lora_bindings"):
            self.assertIn(name, plan["removed"])
        root, child = plan["nodes"]
        self.assertEqual(root["step_id"], "s1")
        self.assertEqual(root["theme_id"], "art_style")
        self.assertEqual(root["class_type"], "S1ThemeRoot")
        self.assertFalse(root["dropped"])
        self.assertIsNone(root["upstream_wire"])
        self.assertEqual(child["class_type"], "S1Theme")
        self.assertEqual(child["theme_id"], "character_pack")
        wire = child["upstream_wire"]
        self.assertEqual(wire["theme_id"], "art_style")
        self.assertNotEqual(wire["theme_id"], "s1")
        self.assertEqual(wire["option_id"], "anime")
        self.assertEqual(wire["op"], "includes_any")
        self.assertTrue(any("rewrite_options" in note for note in child["warnings"]))
        self.assertTrue(any("rewrite_instructions" in note for note in child["warnings"]))
        dup = MIGRATE.plan_sequence(
            {
                "steps": [
                    {"step_id": "s1", "theme_id": "same", "enabled_by_default": True},
                    {"step_id": "s2", "theme_id": "same", "enabled_by_default": False},
                ]
            }
        )
        self.assertTrue(dup["nodes"][1]["dropped"])
        self.assertIsNone(dup["nodes"][1]["class_type"])
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
        self.assertTrue(disabled["nodes"][0]["dropped"])
        self.assertTrue(any("disable_step" in note for note in disabled["nodes"][0]["warnings"]))

    def test_router_graph_becomes_settings_root_and_an_option_wire(self):
        art = json.loads(read_example("theme.art_style.json"))
        pack = json.loads(read_example("theme.character_pack.json"))
        enable = json.loads(_legacy("enable.when_anime.json"))
        secret = "secret-key-not-for-notes"
        source = {
            "nodes": [
                {
                    "id": "art",
                    "class_type": "S1Theme",
                    "run": "enabled",
                    "positive": "anime girl",
                    "negative": "blurry",
                    "theme_json": art,
                    "enable_json": {"match": "any", "clauses": [{"theme_id": "ignored", "op": "answered"}]},
                    "api_key": secret,
                    "api_model": "m",
                    "endpoint": "https://system-one.dev/v1/systemone",
                    "noul_threshold": 0.4,
                    "on_error": "raise",
                    "min_confidence": 0.2,
                },
                {
                    "id": "cast",
                    "class_type": "S1Theme",
                    "run": "when_upstream",
                    "positive": "child",
                    "negative": "",
                    "theme_json": pack,
                    "enable_json": enable,
                    "upstream": ["art", 0],
                    "api_key": secret,
                    "api_model": "m",
                    "endpoint": "https://system-one.dev/v1/systemone",
                    "noul_threshold": 0.4,
                    "on_error": "raise",
                    "min_confidence": 0.2,
                },
                {
                    "id": "off",
                    "class_type": "S1Theme",
                    "run": "disabled",
                    "positive": "",
                    "negative": "",
                    "theme_json": art,
                    "api_key": secret,
                    "api_model": "m",
                },
                {
                    "id": "agg",
                    "class_type": "S1LoraAggregate",
                    "inputs": {"model": ["model", 0], "theme_result": ["cast", 0]},
                },
            ]
        }
        plan = MIGRATE.migrate_router_graph(source)
        for name in ("run", "enable_json", "theme_result", "S1_THEME_RESULT"):
            self.assertIn(name, plan["removed"])
        self.assertEqual(len(plan["settings_nodes"]), 1)
        settings = plan["settings_nodes"][0]
        self.assertEqual(settings["class_type"], "S1Settings")
        self.assertEqual(settings["inputs"]["on_error"], "raise")
        self.assertEqual(settings["inputs"]["noul_threshold"], 0.4)
        self.assertEqual(settings["inputs"]["api_key"], secret)
        notes = " ".join(plan["warnings"])
        self.assertNotIn(secret, notes)
        by_id = {node["id"]: node for node in plan["nodes"]}
        self.assertEqual(by_id["art"]["class_type"], "S1ThemeRoot")
        self.assertNotIn("run", by_id["art"]["inputs"])
        self.assertNotIn("enable_json", by_id["art"]["inputs"])
        self.assertNotIn("api_key", by_id["art"]["inputs"])
        self.assertEqual(list(by_id["art"]["inputs"])[:2], ["positive", "negative"])
        self.assertEqual(by_id["art"]["inputs"]["positive"], "anime girl")
        self.assertEqual(by_id["art"]["inputs"]["negative"], "blurry")
        self.assertEqual(by_id["art"]["inputs"]["settings"], ["settings", 0])
        self.assertEqual(by_id["cast"]["class_type"], "S1Theme")
        self.assertEqual(by_id["cast"]["inputs"]["upstream"], ["art", 0])
        self.assertEqual(plan["wires"][0]["option_id"], "anime")
        self.assertEqual(plan["wires"][0]["output_index"], 0)
        self.assertNotIn("off", by_id)
        self.assertEqual(plan["dropped"][0]["id"], "off")
        self.assertNotIn("theme_result", by_id["agg"]["inputs"])
        self.assertTrue(any("theme_result" in note for note in plan["warnings"]))
        self.assertTrue(any("enable_json is ignored" in note for note in plan["warnings"]))

        split = MIGRATE.migrate_router_graph(
            {
                "9": {
                    "class_type": "S1Theme",
                    "inputs": {
                        "run": "when_upstream",
                        "positive": "p",
                        "negative": "n",
                        "theme_json": json.dumps(art),
                        "enable_json": json.dumps(
                            {
                                "match": "any",
                                "clauses": [
                                    {"theme_id": "art_style", "op": "includes_any", "option_ids": ["anime", "realistic"]}
                                ],
                            }
                        ),
                        "api_key": "",
                    },
                }
            }
        )
        self.assertTrue(any("one Theme copy per option" in note for note in split["warnings"]))
        self.assertIsNone(split["nodes"][0]["upstream_wire"])


if __name__ == "__main__":
    unittest.main()
