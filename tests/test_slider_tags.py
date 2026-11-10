"""Parse tag:weight strings and confirm the decision prompt omits tags."""

from __future__ import annotations

import json
import unittest

from tests.harness import (
    CountingClient,
    option,
    run_theme,
    theme_doc,
)

from s1_lora_router.schema.tags import (
    SLIDER_STRENGTH_MAX,
    SLIDER_STRENGTH_MIN,
    clamp_strength,
    format_chip_label,
    format_tag,
    normalize_library_tags,
    parse_tag,
)


class TagParseTests(unittest.TestCase):
    def test_plain_and_weighted_forms(self):
        plain = parse_tag("age")
        self.assertEqual(plain.name, "age")
        self.assertIsNone(plain.weight)
        self.assertFalse(plain.has_weight)
        self.assertEqual(plain.canonical, "age")

        negative = parse_tag("age:-2")
        self.assertEqual(negative.name, "age")
        self.assertEqual(negative.weight, -2)
        self.assertEqual(negative.canonical, "age:-2")

        plus = parse_tag("age:+1.5")
        self.assertEqual(plus.name, "age")
        self.assertEqual(plus.weight, 1.5)
        self.assertEqual(plus.canonical, "age:1.5")
        self.assertEqual(format_tag("age", 1.5), "age:1.5")

        zero = parse_tag("age:0")
        self.assertEqual(zero.weight, 0)
        self.assertTrue(zero.has_weight)

        spaced = parse_tag("age: -2")
        self.assertEqual(spaced.name, "age")
        self.assertEqual(spaced.weight, -2)

    def test_non_weight_suffixes_stay_in_the_name(self):
        self.assertEqual(parse_tag("foo:bar").name, "foo:bar")
        self.assertIsNone(parse_tag("foo:bar").weight)
        self.assertIsNone(parse_tag("age:\u00b12").weight)
        self.assertEqual(parse_tag("age:").name, "age:")
        self.assertEqual(parse_tag(":-2").name, ":-2")

    def test_chip_label_uses_minus(self):
        self.assertEqual(format_chip_label("age:-2"), "age \u22122")
        self.assertEqual(format_chip_label("age:1.5"), "age 1.5")
        self.assertEqual(format_chip_label("age"), "age")

    def test_library_tags_drop_weights(self):
        self.assertEqual(normalize_library_tags(["age:-2", "Age", "style"]), ["age", "Age", "style"])

    def test_clamp(self):
        self.assertEqual(clamp_strength(1.5), (1.5, False))
        self.assertEqual(clamp_strength(6), (SLIDER_STRENGTH_MAX, True))
        self.assertEqual(clamp_strength(-9), (SLIDER_STRENGTH_MIN, True))


class DecisionPromptOmitsTagsTests(unittest.TestCase):
    """Step 0: the judge does not see option tags or library tags."""

    def test_choice_and_noul_prompts_omit_option_tags(self):
        secret = "slider_secret_tag"
        weighted = "age:-2"
        single_client = CountingClient()
        run_theme(
            theme_json=theme_doc(
                theme_id="style",
                select_mode="single",
                instructions="Choose the look.",
                options=[
                    option("anime", [secret, weighted], label="Anime look", description="An anime drawing"),
                    option("none", [], label="None", description="None"),
                ],
            ),
            client=single_client,
        )
        self.assertTrue(single_client.calls)
        self._assert_payload_omits_tags(single_client.calls[0], [secret, weighted])

        multi_client = CountingClient()
        run_theme(
            theme_json=theme_doc(
                theme_id="traits",
                select_mode="multi",
                instructions="Judge each trait.",
                options=[
                    option("young", [secret, weighted], label="Young", description="Looks young"),
                    option("none", [], label="None", description="None"),
                ],
            ),
            client=multi_client,
        )
        self.assertTrue(multi_client.calls)
        for call in multi_client.calls:
            self._assert_payload_omits_tags(call, [secret, weighted])

    def _assert_payload_omits_tags(self, call, forbidden):
        state, questions = call
        self.assertEqual(set(state), {"positive", "negative"})
        blob = json.dumps({"state": state, "questions": questions}, ensure_ascii=False)
        for token in forbidden:
            self.assertNotIn(token, blob)
        for question in questions.values():
            self.assertNotIn("tags", question)
            self.assertNotIn("option_tags", question)
            self.assertNotIn("loras", question)


if __name__ == "__main__":
    unittest.main()
