"""Executor-level Theme Collect tests.

Direct ``merge()`` / ``collect_decisions()`` calls never reach ComfyUI's
scheduler. These tests drive the 0.44 ``_async_map_node_over_list``
short-circuit (isolated fixture, and the live module when importable) so a
blocked sibling option cannot skip Collect or Aggregate.

They do not call SystemOne, load models, or submit a prompt to a running
server. That is execution-engine evidence, not a full KSampler/Preview
image-generation proof.
"""

from __future__ import annotations

import asyncio
import unittest

from tests.comfy_execution_fixture import (
    ExecutionBlocker as FixtureBlocker,
    run_map,
    try_import_real_execution,
)
import importlib

from tests.harness import (
    PACKAGE_NAME,
    PKG,
    TYPES,
    CountingClient,
    as_payload,
    option,
    run_theme,
    theme_doc,
)

BLOCKER = importlib.import_module(PACKAGE_NAME + ".schema.blocker")

COMPAT = __import__("s1_lora_router.schema.execution_compat", fromlist=["*"])


def _payload(theme_id="t", option_id="a", tags=("tag",)):
    result = run_theme(
        theme_json=theme_doc(
            theme_id=theme_id,
            options=[option(option_id, list(tags))],
        ),
        client=CountingClient(),
    ).result
    return as_payload(result, slot_option_id=option_id)


def _inputs(**kwargs):
    packed = {}
    for key, value in kwargs.items():
        packed[key] = [value]
    return packed


class _RequiredProbe:
    """A required-input consumer, like LoRA Aggregate.decision or a child Theme."""

    FUNCTION = "run"
    RETURN_TYPES = ("INT",)
    called = 0

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"value": ("INT",)}, "optional": {}}

    def run(self, value):
        type(self).called += 1
        self.last = value
        return (value,)


class CollectExecutionMixin:
    """Shared cases. ``blocker_cls`` and ``execute_map`` are provided by subclasses."""

    blocker_cls = FixtureBlocker

    def execute_map(self, obj, input_data_all):
        raise NotImplementedError

    def setUp(self):
        self.collect = PKG.NODE_CLASS_MAPPINGS["S1ThemeCollect"]()
        self.payload_a = _payload("theme_a", "option_1", ("bikini",))
        self.payload_b = _payload("theme_b", "option_2", ("other",))
        _RequiredProbe.called = 0

    def test_class_opts_in_to_optional_blocker_filter(self):
        cls = PKG.NODE_CLASS_MAPPINGS["S1ThemeCollect"]
        self.assertTrue(cls.IGNORE_OPTIONAL_EXECUTION_BLOCKERS)
        self.assertTrue(self.collect.IGNORE_OPTIONAL_EXECUTION_BLOCKERS)

    def test_unpatched_map_skips_collect_when_sibling_is_blocked(self):
        """Root cause: 0.44 skips the node before merge() sees the inputs."""

        blocked = self.blocker_cls(None)
        seen = {"called": 0}
        original = self.collect.merge

        def wrapped(*args, **kwargs):
            seen["called"] += 1
            return original(*args, **kwargs)

        self.collect.merge = wrapped
        raw = run_map(
            self.collect,
            _inputs(a=self.payload_a, b=blocked),
            blocker_cls=self.blocker_cls,
        )
        self.assertEqual(seen["called"], 0)
        self.assertEqual(len(raw), 1)
        self.assertTrue(BLOCKER.is_execution_blocker(raw[0][0]))
        self.assertIsInstance(raw[0][0], self.blocker_cls)

    def test_selecting_a_keeps_decision_and_skips_required_blocked_branch(self):
        blocked = self.blocker_cls(None)
        out = self.execute_map(self.collect, _inputs(a=self.payload_a, b=blocked))
        self.assertEqual(len(out), 1)
        decision = out[0][0]
        self.assertIs(decision, self.payload_a)
        self.assertEqual(decision.slot_option_id, "option_1")
        self.assertEqual(decision.result.tags, ["bikini"])

        probe = _RequiredProbe()
        skipped = self.execute_map(probe, _inputs(value=blocked))
        self.assertEqual(_RequiredProbe.called, 0)
        self.assertTrue(BLOCKER.is_execution_blocker(skipped[0][0]))

        probe2 = _RequiredProbe()
        kept = self.execute_map(probe2, _inputs(value=decision))
        self.assertEqual(_RequiredProbe.called, 1)
        self.assertIs(kept[0][0], decision)

    def test_selecting_b_keeps_decision(self):
        blocked = self.blocker_cls(None)
        out = self.execute_map(self.collect, _inputs(a=blocked, b=self.payload_b))
        decision = out[0][0]
        self.assertIs(decision, self.payload_b)
        self.assertEqual(decision.slot_option_id, "option_2")
        self.assertEqual(decision.result.tags, ["other"])

    def test_missing_branch_passthrough(self):
        out = self.execute_map(self.collect, _inputs(a=self.payload_a))
        self.assertIs(out[0][0], self.payload_a)
        out_b = self.execute_map(self.collect, _inputs(b=self.payload_b))
        self.assertIs(out_b[0][0], self.payload_b)

    def test_both_blocked_raises(self):
        blocked = self.blocker_cls(None)
        with self.assertRaises(TYPES.SchemaError) as ctx:
            self.execute_map(self.collect, _inputs(a=blocked, b=blocked))
        self.assertIn("a or b", str(ctx.exception))

    def test_no_inputs_raises(self):
        with self.assertRaises(TYPES.SchemaError) as ctx:
            self.execute_map(self.collect, {})
        self.assertIn("a or b", str(ctx.exception))

    def test_two_live_branches_still_merge(self):
        out = self.execute_map(self.collect, _inputs(a=self.payload_a, b=self.payload_b))
        merged = out[0][0]
        self.assertEqual(merged.emitted_reason, "collected")
        self.assertEqual(
            [item.theme_id for item in merged.result.decisions],
            ["theme_a", "theme_b"],
        )

    def test_filter_leaves_required_blocker_in_place(self):
        blocked = self.blocker_cls(None)
        payload = {"value": [blocked], "a": [blocked]}
        # Probe does not opt in; dropping must not happen.
        kept = COMPAT.drop_optional_execution_blockers(
            _RequiredProbe(), payload, blocker_cls=self.blocker_cls
        )
        self.assertIs(kept, payload)
        self.assertIn("value", kept)

    def test_drop_only_optional_blockers_on_collect(self):
        blocked = self.blocker_cls(None)
        packed = _inputs(a=self.payload_a, b=blocked)
        filtered = COMPAT.drop_optional_execution_blockers(
            self.collect, packed, blocker_cls=self.blocker_cls
        )
        self.assertEqual(list(filtered.keys()), ["a"])
        self.assertIs(filtered["a"][0], self.payload_a)


class TestCollectExecutionFixture(CollectExecutionMixin, unittest.TestCase):
    """Isolated 0.44 short-circuit with the optional-blocker filter applied."""

    blocker_cls = FixtureBlocker

    def execute_map(self, obj, input_data_all):
        filtered = COMPAT.drop_optional_execution_blockers(
            obj, input_data_all, blocker_cls=self.blocker_cls
        )
        return run_map(obj, filtered, blocker_cls=self.blocker_cls)


@unittest.skipUnless(try_import_real_execution() is not None, "ComfyUI execution module is not importable")
class TestCollectExecutionComfyUI(CollectExecutionMixin, unittest.TestCase):
    """Same cases against the live ComfyUI 0.44 map function, after the hook."""

    def setUp(self):
        real = try_import_real_execution()
        self.assertIsNotNone(real)
        self.exe, self.blocker_cls = real
        status = COMPAT.patch_comfy_execution()
        self.assertIn(status, {"applied", "already"})
        super().setUp()

    def execute_map(self, obj, input_data_all):
        return_values = asyncio.run(
            self.exe._async_map_node_over_list(
                "prompt",
                "node",
                obj,
                input_data_all,
                obj.FUNCTION,
                allow_interrupt=False,
            )
        )
        from tests.comfy_execution_fixture import expand_return

        return expand_return(return_values, obj, blocker_cls=self.blocker_cls)

    def test_unpatched_map_skips_collect_when_sibling_is_blocked(self):
        """Use the unwrapped 0.44 function to re-state the root cause on this runtime."""

        original = getattr(self.exe._async_map_node_over_list, "__wrapped__", None)
        if original is None:
            self.skipTest("hook wrapper lost the original map function")
        blocked = self.blocker_cls(None)
        seen = {"called": 0}
        merge = self.collect.merge

        def wrapped(*args, **kwargs):
            seen["called"] += 1
            return merge(*args, **kwargs)

        self.collect.merge = wrapped
        return_values = asyncio.run(
            original(
                "prompt",
                "node",
                self.collect,
                _inputs(a=self.payload_a, b=blocked),
                self.collect.FUNCTION,
                allow_interrupt=False,
            )
        )
        self.assertEqual(seen["called"], 0)
        self.assertTrue(BLOCKER.is_execution_blocker(return_values[0]))
        self.assertIsInstance(return_values[0], self.blocker_cls)


if __name__ == "__main__":
    unittest.main()
