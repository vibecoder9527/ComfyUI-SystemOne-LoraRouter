"""Theme decisions, enable trees, none, and error policy. Clients are injected."""

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
    clause,
    enable_doc,
    option,
    read_example,
    run_theme,
    theme_doc,
)


ART = "theme.art_style.json"
PACK = "theme.character_pack.json"


class ThemeEngineTests(unittest.TestCase):
    def test_disabled_skips_api_and_empty_theme_is_valid(self):
        client = CountingClient()
        with mock.patch("urllib.request.urlopen") as urlopen:
            outcome = run_theme(
                theme_json=read_example("theme.empty.json"),
                run="disabled",
                enable_json=read_example("enable.empty.json"),
                client=client,
                api_key="sekret-token-xyz",
            )
        urlopen.assert_not_called()
        self.assertEqual(client.calls, [])
        self.assertEqual(outcome.result.tags, [])
        self.assertEqual(outcome.result.decisions[0].status, "skipped")
        self.assertEqual(outcome.result.decisions[0].reason, "disabled")
        self.assertFalse(outcome.result.decisions[0].enabled)
        self.assertFalse(outcome.report["api"]["called"])
        self.assertEqual(outcome.report["api"]["key_source"], "widget")
        self.assertNotIn("sekret-token-xyz", ENGINE.dump_report(outcome.report))
        self.assertIn("run=disabled", " ".join(outcome.report["notes"]))

    def test_disabled_still_rejects_bad_json_without_http(self):
        client = CountingClient()
        with mock.patch("urllib.request.urlopen") as urlopen:
            with self.assertRaises(TYPES.SchemaError):
                run_theme(theme_json="{", run="disabled", client=client)
            with self.assertRaises(TYPES.SchemaError):
                run_theme(
                    run="disabled",
                    enable_json="{",
                    client=client,
                )
        urlopen.assert_not_called()
        self.assertEqual(client.calls, [])

    def test_enabled_ignores_unmatched_rules_and_when_upstream_does_not(self):
        client = CountingClient()
        blocked = enable_doc([clause("missing", "includes_any", ["anime"])])
        document = theme_doc(options=[option("a", ["tag"]), option("b", ["other"])])
        forced = run_theme(theme_json=document, run="enabled", enable_json=blocked, client=client)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(forced.report["status"], "ok")
        self.assertEqual(forced.result.tags, ["tag"])
        self.assertTrue(forced.report["api"]["called"])
        quiet = CountingClient()
        skipped = run_theme(
            theme_json=document,
            run="when_upstream",
            enable_json=blocked,
            client=quiet,
        )
        self.assertEqual(quiet.calls, [])
        self.assertFalse(skipped.report["api"]["called"])
        self.assertEqual(skipped.result.decisions[0].reason, "enable_rules_unmatched")
        empty = CountingClient()
        run_theme(
            theme_json=document,
            run="when_upstream",
            enable_json=enable_doc(),
            upstream=None,
            client=empty,
        )
        self.assertEqual(empty.calls, [])

    def test_enable_tree_is_deterministic(self):
        root_client = FixedChoiceClient("anime")
        root = run_theme(
            theme_json=read_example(ART),
            run="enabled",
            positive="anime girl",
            negative="blurry",
            client=root_client,
            api_key="sekret-token-xyz",
        )
        self.assertEqual(root.result.decisions[0].selected, ["anime"])
        self.assertEqual(root.result.tags, ["style_anime"])
        self.assertEqual(root_client.calls[0][0], {"positive": "anime girl", "negative": "blurry"})
        self.assertEqual(root_client.calls[0][1]["art_style"]["type"], "choice")
        self.assertNotIn("sekret-token-xyz", ENGINE.dump_report(root.report))

        mid_client = CountingClient()
        mid = run_theme(
            theme_json=theme_doc(theme_id="mid", options=[option("go", ["mid_tag"])]),
            run="disabled",
            upstream=root.result,
            positive="should-not-send",
            client=mid_client,
        )
        self.assertEqual(mid_client.calls, [])
        self.assertEqual(mid.result.tags, ["style_anime"])
        self.assertEqual(mid.result.get("mid").status, "skipped")

        child_client = ScoreClient({"waifu_a": 0.9, "waifu_b": 0.2})
        child = run_theme(
            theme_json=read_example(PACK),
            run="when_upstream",
            enable_json=read_example("enable.when_anime.json"),
            upstream=mid.result,
            positive="child",
            negative="",
            client=child_client,
            noul_threshold=0.5,
        )
        self.assertEqual(len(child_client.calls), 1)
        self.assertEqual(child_client.calls[0][0], {"positive": "child", "negative": ""})
        questions = child_client.calls[0][1]
        self.assertEqual(set(questions), {"character_pack__waifu_a", "character_pack__waifu_b"})
        self.assertIn("具體選項", questions["character_pack__waifu_a"]["instructions"])
        self.assertIn("是否應啟用此選項", questions["character_pack__waifu_a"]["instructions"])
        self.assertTrue(questions["character_pack__waifu_a"]["instructions"].startswith("是否套用角色 LoRA"))
        self.assertEqual(child.result.get("character_pack").selected, ["waifu_a"])
        self.assertEqual(child.result.tags, ["style_anime", "char_a"])

        leaf_client = CountingClient()
        leaf = run_theme(
            theme_json=theme_doc(theme_id="leaf", options=[option("yes", ["leaf_tag"]), option("no")]),
            run="when_upstream",
            enable_json=enable_doc([clause("mid", "skipped")]),
            upstream=child.result,
            client=leaf_client,
        )
        self.assertEqual(leaf.result.get("leaf").selected, ["yes"])
        self.assertEqual(leaf.result.tags, ["style_anime", "char_a", "leaf_tag"])
        neq_client = CountingClient()
        neq = run_theme(
            theme_json=theme_doc(
                theme_id="neq_leaf",
                options=[option("yes", ["nope"]), option("alt")],
            ),
            run="when_upstream",
            enable_json=enable_doc([clause("mid", "neq", ["go"])]),
            upstream=child.result,
            client=neq_client,
        )
        self.assertEqual(neq_client.calls, [])
        self.assertEqual(neq.result.get("neq_leaf").status, "skipped")
        self.assertNotIn("nope", neq.result.tags)

    def test_match_all_eq_includes_and_answered(self):
        upstream = run_theme(
            theme_json=theme_doc(
                theme_id="art_style",
                options=[option("anime", ["style_anime"]), option("realistic"), option("none")],
            ),
            client=FixedChoiceClient("anime"),
        ).result
        self.assertTrue(
            ENGINE.rules_match(
                TYPES.parse_enable_rules(
                    enable_doc(
                        [
                            clause("art_style", "eq", ["anime"]),
                            clause("art_style", "includes_all", ["anime"]),
                        ],
                        match="all",
                    )
                ),
                upstream,
            )
        )
        self.assertFalse(
            ENGINE.rules_match(
                TYPES.parse_enable_rules(
                    enable_doc(
                        [
                            clause("art_style", "eq", ["anime"]),
                            clause("art_style", "eq", ["realistic"]),
                        ],
                        match="all",
                    )
                ),
                upstream,
            )
        )
        self.assertTrue(
            ENGINE.rules_match(
                TYPES.parse_enable_rules(enable_doc([clause("art_style", "answered")])),
                upstream,
            )
        )
        self.assertFalse(ENGINE.rules_match(TYPES.parse_enable_rules(enable_doc()), upstream))
        multi = run_theme(
            theme_json=theme_doc(
                theme_id="pack",
                select_mode="multi",
                options=[option("waifu_a"), option("waifu_b")],
            ),
            client=ScoreClient({"waifu_a": 1, "waifu_b": 1}),
        ).result
        self.assertFalse(
            ENGINE.rules_match(
                TYPES.parse_enable_rules(enable_doc([clause("pack", "eq", ["waifu_a"])])),
                multi,
            )
        )
        self.assertTrue(
            ENGINE.rules_match(
                TYPES.parse_enable_rules(
                    enable_doc([clause("pack", "includes_all", ["waifu_a", "waifu_b"])])
                ),
                multi,
            )
        )

    def test_realistic_choice_does_not_enable_the_character_theme(self):
        root = run_theme(
            theme_json=read_example(ART),
            client=FixedChoiceClient("realistic"),
        )
        self.assertEqual(root.result.tags, ["style_realistic"])
        child = CountingClient()
        outcome = run_theme(
            theme_json=read_example(PACK),
            run="when_upstream",
            enable_json=read_example("enable.when_anime.json"),
            upstream=root.result,
            client=child,
        )
        self.assertEqual(child.calls, [])
        self.assertEqual(outcome.result.get("character_pack").status, "skipped")
        self.assertEqual(outcome.result.tags, ["style_realistic"])

    def test_none_contributes_no_tags_but_remains_selectable(self):
        root = run_theme(
            theme_json=read_example(ART),
            client=FixedChoiceClient("none"),
        )
        self.assertEqual(root.result.decisions[0].selected, ["none"])
        self.assertEqual(root.result.tags, [])
        self.assertEqual(root.result.decisions[0].option_tags, [])
        nxt = run_theme(
            theme_json=theme_doc(theme_id="after_none", options=[option("go", ["after"])]),
            run="when_upstream",
            enable_json=enable_doc([clause("art_style", "eq", ["none"])]),
            upstream=root.result,
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

    def test_enabled_theme_with_no_options_does_not_call(self):
        client = CountingClient()
        outcome = run_theme(
            theme_json=read_example("theme.empty.json"),
            run="enabled",
            on_error="passthrough",
            client=client,
        )
        self.assertEqual(client.calls, [])
        self.assertFalse(outcome.report["api"]["called"])
        self.assertEqual(outcome.result.decisions[0].status, "error")
        self.assertIn("no options", outcome.result.errors[0])
        with self.assertRaises(ENGINE.ThemeError) as ctx:
            run_theme(
                theme_json=read_example("theme.empty.json"),
                run="enabled",
                on_error="raise",
                client=CountingClient(),
            )
        self.assertFalse(ctx.exception.report["api"]["called"])

    def test_duplicate_theme_id_raises_before_http(self):
        first = run_theme(theme_json=theme_doc(theme_id="art_style"), client=CountingClient())
        client = CountingClient()
        with mock.patch("urllib.request.urlopen") as urlopen:
            with self.assertRaises(TYPES.SchemaError) as ctx:
                run_theme(
                    theme_json=theme_doc(theme_id="art_style"),
                    run="disabled",
                    upstream=first.result,
                    client=client,
                )
        urlopen.assert_not_called()
        self.assertEqual(client.calls, [])
        self.assertIn("art_style", str(ctx.exception))

    def test_api_error_passthrough_and_bad_widgets(self):
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
        with self.assertRaises(TYPES.SchemaError):
            run_theme(run="sometimes")
        with self.assertRaises(TYPES.SchemaError):
            run_theme(endpoint="ftp://example.test", client=CountingClient())
        with self.assertRaises(TYPES.SchemaError):
            run_theme(upstream="nope", client=CountingClient())
        with self.assertRaises(TYPES.SchemaError):
            run_theme(min_confidence=2, client=CountingClient())

    def test_live_client_is_mocked_and_report_omits_the_key(self):
        secret = "sekret-token-xyz"
        with mock.patch("urllib.request.urlopen", side_effect=canned_urlopen) as urlopen:
            outcome = ENGINE.run_theme(
                theme_json=read_example(ART),
                positive="p",
                negative="n",
                run="enabled",
                enable_json=read_example("enable.empty.json"),
                api_key=secret,
                api_model="my-model",
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


if __name__ == "__main__":
    unittest.main()
