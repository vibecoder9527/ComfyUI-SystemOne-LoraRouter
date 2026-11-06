"""Theme decisions, option slots, none, and error policy. Clients are injected."""

from __future__ import annotations

import unittest
from unittest import mock

from tests.harness import (
    CLIENT,
    ENGINE,
    TYPES,
    CountingClient,
    FixedChoiceClient,
    ScoreClient,
    canned_urlopen,
    make_settings,
    option,
    read_example,
    run_theme,
    theme_doc,
)


ART = "theme.art_style.json"
PACK = "theme.character_pack.json"


def _slots(outcome, theme_json):
    theme = TYPES.parse_theme(theme_json)
    values = ENGINE.option_slot_values(theme, outcome.result)
    by_id = {}
    for option_def, value in zip(theme.options, values):
        by_id[option_def.option_id] = value
    return by_id


class ThemeEngineTests(unittest.TestCase):
    def test_settings_are_required_and_empty_theme_does_not_call(self):
        client = CountingClient()
        with mock.patch("urllib.request.urlopen") as urlopen:
            outcome = run_theme(
                theme_json=read_example("theme.empty.json"),
                settings=make_settings(api_key="sekret-token-xyz", on_error="passthrough"),
                client=client,
            )
        urlopen.assert_not_called()
        self.assertEqual(client.calls, [])
        self.assertEqual(outcome.result.tags, [])
        self.assertEqual(outcome.result.decisions[0].status, "error")
        self.assertIn("no options", outcome.result.errors[0])
        self.assertFalse(outcome.report["api"]["called"])
        self.assertEqual(outcome.report["role"], "root")
        self.assertEqual(outcome.report["api"]["key_source"], "widget")
        self.assertNotIn("sekret-token-xyz", ENGINE.dump_report(outcome.report))
        self.assertEqual(ENGINE.option_slot_values(TYPES.parse_theme(read_example("theme.empty.json")), outcome.result), [])
        with self.assertRaises(TYPES.SchemaError):
            ENGINE.run_theme(
                theme_json=read_example("theme.empty.json"),
                positive="p",
                negative="",
                settings="nope",
                client=client,
            )

    def test_bad_json_and_bad_settings_do_not_call(self):
        client = CountingClient()
        with mock.patch("urllib.request.urlopen") as urlopen:
            with self.assertRaises(TYPES.SchemaError):
                run_theme(theme_json="{", client=client)
            with self.assertRaises(TYPES.SchemaError):
                make_settings(endpoint="ftp://example.test")
            with self.assertRaises(TYPES.SchemaError):
                make_settings(on_error="sometimes")
            with self.assertRaises(TYPES.SchemaError):
                make_settings(min_confidence=2)
            with self.assertRaises(TYPES.SchemaError):
                run_theme(upstream="nope", client=client)
        urlopen.assert_not_called()
        self.assertEqual(client.calls, [])

    def test_root_then_child_accumulates_tags(self):
        root_client = FixedChoiceClient("anime")
        root = run_theme(
            theme_json=read_example(ART),
            positive="anime girl",
            negative="blurry",
            client=root_client,
            api_key="sekret-token-xyz",
        )
        self.assertEqual(root.result.decisions[0].selected, ["anime"])
        self.assertEqual(root.result.tags, ["style_anime"])
        self.assertEqual(root_client.calls[0][0], {"positive": "anime girl", "negative": "blurry"})
        omitted_client = FixedChoiceClient("anime")
        omitted = run_theme(
            theme_json=read_example(ART),
            positive="anime girl",
            negative=None,
            client=omitted_client,
        )
        self.assertEqual(omitted_client.calls[0][0], {"positive": "anime girl", "negative": ""})
        self.assertEqual(root_client.calls[0][1]["art_style"]["type"], "choice")
        self.assertNotIn("sekret-token-xyz", ENGINE.dump_report(root.report))
        slots = _slots(root, read_example(ART))
        self.assertEqual(slots["anime"].result.tags, ["style_anime"])
        self.assertEqual(slots["anime"].slot_option_id, "anime")
        self.assertTrue(ENGINE.is_execution_blocker(slots["realistic"]))
        self.assertTrue(ENGINE.is_execution_blocker(slots["none"]))
        self.assertIs(slots["anime"].result, root.result)

        child_client = ScoreClient({"waifu_a": 0.9, "waifu_b": 0.2})
        child = run_theme(
            theme_json=read_example(PACK),
            upstream=slots["anime"],
            positive="child",
            negative="",
            client=child_client,
            noul_threshold=0.5,
        )
        self.assertEqual(child.report["role"], "downstream")
        self.assertEqual(len(child_client.calls), 1)
        self.assertEqual(child_client.calls[0][0], {"positive": "child", "negative": ""})
        questions = child_client.calls[0][1]
        self.assertEqual(set(questions), {"character_pack__waifu_a", "character_pack__waifu_b"})
        self.assertIn("具體選項", questions["character_pack__waifu_a"]["instructions"])
        self.assertIn("是否應啟用此選項", questions["character_pack__waifu_a"]["instructions"])
        self.assertTrue(questions["character_pack__waifu_a"]["instructions"].startswith("是否套用角色 LoRA"))
        self.assertEqual(child.result.get("character_pack").selected, ["waifu_a"])
        self.assertEqual(child.result.tags, ["style_anime", "char_a"])
        child_slots = _slots(child, read_example(PACK))
        self.assertEqual(child_slots["waifu_a"].emitted_reason, "selected")
        self.assertTrue(ENGINE.is_execution_blocker(child_slots["waifu_b"]))

    def test_unselected_slot_is_a_blocker_and_multi_shares_one_result(self):
        root = run_theme(
            theme_json=read_example(ART),
            client=FixedChoiceClient("realistic"),
        )
        slots = _slots(root, read_example(ART))
        self.assertEqual(root.result.tags, ["style_realistic"])
        self.assertTrue(ENGINE.is_execution_blocker(slots["anime"]))
        self.assertEqual(slots["realistic"].slot_option_id, "realistic")
        self.assertIsNone(slots["anime"].message)
        multi = run_theme(
            theme_json=theme_doc(
                theme_id="pack",
                select_mode="multi",
                options=[option("waifu_a", ["char_a"]), option("waifu_b", ["char_b"])],
            ),
            client=ScoreClient({"waifu_a": 1, "waifu_b": 1}),
        )
        both = _slots(multi, theme_doc(
            theme_id="pack",
            select_mode="multi",
            options=[option("waifu_a", ["char_a"]), option("waifu_b", ["char_b"])],
        ))
        self.assertIs(both["waifu_a"].result, both["waifu_b"].result)
        self.assertEqual(both["waifu_a"].result.tags, ["char_a", "char_b"])
        quiet = run_theme(
            theme_json=theme_doc(
                theme_id="pack",
                select_mode="multi",
                options=[option("waifu_a", ["char_a"]), option("waifu_b", ["char_b"])],
            ),
            client=ScoreClient({"waifu_a": 0.1, "waifu_b": 0.1}),
        )
        none_selected = _slots(quiet, theme_doc(
            theme_id="pack",
            select_mode="multi",
            options=[option("waifu_a", ["char_a"]), option("waifu_b", ["char_b"])],
        ))
        self.assertTrue(ENGINE.is_execution_blocker(none_selected["waifu_a"]))
        self.assertTrue(ENGINE.is_execution_blocker(none_selected["waifu_b"]))
        self.assertEqual(quiet.result.get("pack").selected, [])

    def test_none_contributes_no_tags_but_its_slot_still_emits(self):
        root = run_theme(
            theme_json=read_example(ART),
            client=FixedChoiceClient("none"),
        )
        self.assertEqual(root.result.decisions[0].selected, ["none"])
        self.assertEqual(root.result.tags, [])
        self.assertEqual(root.result.decisions[0].option_tags, [])
        slots = _slots(root, read_example(ART))
        self.assertEqual(slots["none"].emitted_reason, "selected")
        self.assertEqual(slots["none"].result.tags, [])
        self.assertTrue(ENGINE.is_execution_blocker(slots["anime"]))
        nxt = run_theme(
            theme_json=theme_doc(theme_id="after_none", options=[option("go", ["after"])]),
            upstream=slots["none"],
            client=CountingClient(),
        )
        self.assertEqual(nxt.result.get("after_none").selected, ["go"])
        self.assertEqual(nxt.result.tags, ["after"])
        mixed = run_theme(
            theme_json=theme_doc(
                theme_id="mix",
                select_mode="multi",
                none_option_id="none",
                options=[option("none", ["should_not_apply"]), option("waifu_a", ["char_a"])],
            ),
            client=ScoreClient({"none": 1, "waifu_a": 1}),
        )
        self.assertEqual(mixed.result.decisions[0].selected, ["none", "waifu_a"])
        self.assertEqual(mixed.result.tags, ["char_a"])
        self.assertEqual(mixed.result.decisions[0].option_tags, [("waifu_a", ["char_a"])])
        mixed_slots = _slots(
            mixed,
            theme_doc(
                theme_id="mix",
                select_mode="multi",
                none_option_id="none",
                options=[option("none", ["should_not_apply"]), option("waifu_a", ["char_a"])],
            ),
        )
        self.assertEqual(mixed_slots["none"].result.tags, ["char_a"])
        self.assertEqual(mixed_slots["waifu_a"].result.tags, ["char_a"])

    def test_single_option_skips_api_and_noul_batches(self):
        client = CountingClient()
        with mock.patch("urllib.request.urlopen") as urlopen:
            outcome = run_theme(
                theme_json=theme_doc(options=[option("only", ["only_tag"])]),
                client=client,
            )
        urlopen.assert_not_called()
        self.assertEqual(client.calls, [])
        self.assertFalse(outcome.report["api"]["called"])
        self.assertEqual(outcome.result.decisions[0].selected, ["only"])
        self.assertTrue(outcome.result.decisions[0].raw["skipped_api"])
        self.assertEqual(outcome.result.tags, ["only_tag"])

        options = [option(f"opt{i}", [f"t{i}"]) for i in range(33)]
        client = CountingClient()
        outcome = run_theme(
            theme_json=theme_doc(select_mode="multi", options=options),
            positive="p",
            negative="n",
            client=client,
        )
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(len(client.calls[0][1]), 32)
        self.assertEqual(len(client.calls[1][1]), 1)
        self.assertEqual(client.calls[0][0], client.calls[1][0])
        self.assertEqual(len(outcome.result.decisions[0].selected), 33)
        self.assertTrue(outcome.report["api"]["called"])

    def test_low_confidence_is_kept_and_invalid_choice_fails(self):
        low = run_theme(
            theme_json=read_example(ART),
            min_confidence=0.5,
            client=FixedChoiceClient("anime", confidence=0.1),
        )
        self.assertEqual(low.result.decisions[0].selected, ["anime"])
        self.assertEqual(low.result.decisions[0].raw["decision"], "low_confidence_kept")
        self.assertTrue(any("low-confidence" in note for note in low.report["notes"]))
        boundary = run_theme(
            theme_json=read_example(ART),
            min_confidence=0.5,
            client=FixedChoiceClient("anime", confidence=0.5),
        )
        self.assertNotIn("decision", boundary.result.decisions[0].raw)
        missing = run_theme(
            theme_json=read_example(ART),
            min_confidence=0.9,
            client=FixedChoiceClient("anime", include_confidence=False),
        )
        self.assertNotIn("decision", missing.result.decisions[0].raw)
        with self.assertRaises(ENGINE.ThemeError) as ctx:
            run_theme(
                theme_json=read_example(ART),
                on_error="raise",
                client=FixedChoiceClient("nope"),
            )
        self.assertIn("nope", str(ctx.exception))
        self.assertIn("art_style", str(ctx.exception))
        self.assertEqual(ctx.exception.result.get("art_style").status, "error")
        self.assertTrue(ctx.exception.report["api"]["called"])
        self.assertNotIn("on_error=passthrough", " ".join(ctx.exception.report["notes"]))

        kept = run_theme(
            theme_json=theme_doc(
                theme_id="other",
                options=[option("a", ["new"]), option("b")],
            ),
            on_error="passthrough",
            upstream=low.result,
            client=FixedChoiceClient("nope"),
        )
        self.assertEqual(kept.result.tags, ["style_anime"])
        self.assertEqual(kept.result.get("other").status, "error")
        self.assertEqual(kept.result.get("other").tags, [])
        self.assertIn("on_error=passthrough: this theme added no tags.", kept.report["notes"])
        self.assertTrue(kept.report["api"]["called"])
        kept_slots = _slots(
            kept,
            theme_doc(theme_id="other", options=[option("a", ["new"]), option("b")]),
        )
        self.assertEqual(kept_slots["a"].emitted_reason, "passthrough_error")
        self.assertEqual(kept_slots["b"].emitted_reason, "passthrough_error")
        self.assertEqual(kept_slots["a"].result.tags, ["style_anime"])

    def test_duplicate_theme_id_raises_before_http(self):
        first = run_theme(theme_json=theme_doc(theme_id="art_style"), client=CountingClient())
        client = CountingClient()
        with mock.patch("urllib.request.urlopen") as urlopen:
            with self.assertRaises(TYPES.SchemaError) as ctx:
                run_theme(
                    theme_json=theme_doc(theme_id="art_style"),
                    upstream=first.result,
                    client=client,
                )
        urlopen.assert_not_called()
        self.assertEqual(client.calls, [])
        self.assertIn("art_style", str(ctx.exception))

    def test_api_error_passthrough(self):
        class Boom(CLIENT.SystemOneClient):
            def __init__(self):
                super().__init__(api_key="k", model="m")
                self.calls = 0

            def decide(self, state, questions):
                self.calls += 1
                raise CLIENT.SystemOneError("down")

        boom = Boom()
        outcome = run_theme(
            theme_json=theme_doc(options=[option("a", ["tag"]), option("b")]),
            on_error="passthrough",
            client=boom,
        )
        self.assertEqual(boom.calls, 1)
        self.assertEqual(outcome.result.decisions[0].status, "error")
        self.assertTrue(outcome.report["api"]["called"])
        self.assertIn("SystemOne: down", outcome.result.errors[0])
        slots = _slots(outcome, theme_doc(options=[option("a", ["tag"]), option("b")]))
        self.assertEqual(slots["a"].emitted_reason, "passthrough_error")
        self.assertEqual(slots["b"].emitted_reason, "passthrough_error")

    def test_live_client_is_mocked_and_report_omits_the_key(self):
        secret = "sekret-token-xyz"
        with mock.patch("urllib.request.urlopen", side_effect=canned_urlopen) as urlopen:
            outcome = ENGINE.run_theme(
                theme_json=read_example(ART),
                positive="p",
                negative="n",
                settings=make_settings(api_key=secret, api_model="my-model"),
            )
        self.assertGreaterEqual(urlopen.call_count, 1)
        self.assertTrue(outcome.report["api"]["called"])
        self.assertEqual(outcome.report["api"]["model"], "my-model")
        self.assertEqual(outcome.report["api"]["key_source"], "widget")
        self.assertFalse(outcome.report["api"]["stub"])
        text = ENGINE.dump_report(outcome.report)
        self.assertNotIn(secret, text)
        self.assertNotIn("option_tags", text)
        self.assertIn('"api":{', text)
        non_ascii = ENGINE.dump_report({"label": "畫風"})
        self.assertIn("畫風", non_ascii)
        self.assertNotIn("\\u", non_ascii)

    def test_threshold_boundary_and_bad_noul(self):
        selected = run_theme(
            theme_json=theme_doc(
                select_mode="multi",
                options=[option("a", ["ta"]), option("b", ["tb"])],
            ),
            noul_threshold=0.5,
            client=ScoreClient({"a": 0.5, "b": 0.49}),
        )
        self.assertEqual(selected.result.decisions[0].selected, ["a"])
        self.assertEqual(selected.result.tags, ["ta"])
        slots = _slots(
            selected,
            theme_doc(select_mode="multi", options=[option("a", ["ta"]), option("b", ["tb"])]),
        )
        self.assertEqual(slots["a"].emitted_reason, "selected")
        self.assertTrue(ENGINE.is_execution_blocker(slots["b"]))

        class BoolNoul(CLIENT.SystemOneClient):
            def __init__(self):
                super().__init__(api_key="k", model="m")

            def decide(self, state, questions):
                return {"answers": {qid: {"noul": True} for qid in questions}}

        outcome = run_theme(
            theme_json=theme_doc(select_mode="multi", options=[option("a"), option("b")]),
            on_error="passthrough",
            client=BoolNoul(),
        )
        self.assertEqual(outcome.result.decisions[0].status, "error")
        self.assertTrue(outcome.report["api"]["called"])

    def test_downstream_without_upstream_raises_before_http(self):
        client = CountingClient()
        with self.assertRaises(TYPES.SchemaError):
            run_theme(
                theme_json=theme_doc(options=[option("a")]),
                role="downstream",
                upstream=None,
                client=client,
            )
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
