"""Unit tests for Theme Collect hook hardening (warnings, signature, stacking, inheritance, mixed batch)."""

from __future__ import annotations

import asyncio
import importlib
import sys
import types
import unittest
import warnings

from tests.harness import PACKAGE_NAME, PKG

COMPAT = importlib.import_module(PACKAGE_NAME + ".schema.execution_compat")

_MISSING = object()


class Blocker:
    def __init__(self, message=None):
        self.message = message


Blocker.__name__ = "ExecutionBlocker"


class DeclaredCollect:
    IGNORE_OPTIONAL_EXECUTION_BLOCKERS = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}, "optional": {"a": ("T",), "b": ("T",)}}


class RequiredSink:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"value": ("T",)}, "optional": {}}


class BareSubclass(DeclaredCollect):
    """Does not re-declare the flag."""


class DeclaredSubclass(DeclaredCollect):
    IGNORE_OPTIONAL_EXECUTION_BLOCKERS = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {"a": ("T",), "b": ("T",), "extra": ("T",)},
        }


class HookCompatTests(unittest.TestCase):
    def setUp(self):
        self._saved_execution = sys.modules.get("execution", _MISSING)

    def tearDown(self):
        if self._saved_execution is _MISSING:
            sys.modules.pop("execution", None)
        else:
            sys.modules["execution"] = self._saved_execution

    def test_product_collect_declares_the_flag_on_its_own_class(self):
        collect = PKG.NODE_CLASS_MAPPINGS["S1ThemeCollect"]
        self.assertIs(collect.__dict__.get("IGNORE_OPTIONAL_EXECUTION_BLOCKERS"), True)
        self.assertTrue(COMPAT.drop_optional_execution_blockers is not None)

    def test_required_blocker_is_not_modified(self):
        blocked = Blocker(None)
        packed = {"value": [blocked]}
        kept = COMPAT.drop_optional_execution_blockers(
            RequiredSink(), packed, blocker_cls=Blocker
        )
        self.assertIs(kept, packed)
        self.assertIs(kept["value"][0], blocked)

    def test_required_mixed_batch_keeps_live_and_blocker_in_place(self):
        live = object()
        blocked = Blocker(None)
        packed = {"value": [live, blocked]}
        kept = COMPAT.drop_optional_execution_blockers(
            RequiredSink(), packed, blocker_cls=Blocker
        )
        self.assertIs(kept, packed)
        self.assertIs(kept["value"][0], live)
        self.assertIs(kept["value"][1], blocked)

    def test_undeclared_subclass_does_not_inherit_the_filter(self):
        live = object()
        packed = {"a": [live], "b": [Blocker(None)]}
        kept = COMPAT.drop_optional_execution_blockers(
            BareSubclass(), packed, blocker_cls=Blocker
        )
        self.assertIs(kept, packed)
        self.assertIn("b", kept)

    def test_declared_subclass_filters_its_own_optional_sockets(self):
        live = object()
        packed = {"a": [live], "extra": [Blocker(None)]}
        filtered = COMPAT.drop_optional_execution_blockers(
            DeclaredSubclass(), packed, blocker_cls=Blocker
        )
        self.assertEqual(list(filtered.keys()), ["a"])
        self.assertIs(filtered["a"][0], live)

    def test_mixed_optional_sequence_keeps_live_items_and_leaves_blockers(self):
        live0 = object()
        live1 = object()
        blocked = Blocker(None)
        packed = {"a": [live0, blocked, live1]}
        filtered = COMPAT.drop_optional_execution_blockers(
            DeclaredCollect(), packed, blocker_cls=Blocker
        )
        self.assertIs(filtered, packed)
        self.assertEqual(len(filtered["a"]), 3)
        self.assertIs(filtered["a"][0], live0)
        self.assertIs(filtered["a"][1], blocked)
        self.assertIs(filtered["a"][2], live1)

    def test_undeclared_dynamic_optional_blocker_is_dropped(self):
        """Frontend-added Collect sockets may not appear in INPUT_TYPES yet."""
        live = object()
        packed = {"a": [live], "z": [Blocker(None)]}
        filtered = COMPAT.drop_optional_execution_blockers(
            DeclaredCollect(), packed, blocker_cls=Blocker
        )
        self.assertEqual(list(filtered.keys()), ["a"])
        self.assertIs(filtered["a"][0], live)

        collect = PKG.NODE_CLASS_MAPPINGS["S1ThemeCollect"]()
        packed = {"a": [live], "q": [Blocker(None)]}
        filtered = COMPAT.drop_optional_execution_blockers(
            collect, packed, blocker_cls=Blocker
        )
        self.assertEqual(list(filtered.keys()), ["a"])

    def test_all_blocker_optional_sequence_is_dropped(self):
        packed = {"a": [Blocker(None), Blocker("x")], "b": [object()]}
        filtered = COMPAT.drop_optional_execution_blockers(
            DeclaredCollect(), packed, blocker_cls=Blocker
        )
        self.assertEqual(list(filtered.keys()), ["b"])

    def test_tuple_mixed_sequence_is_left_unchanged(self):
        live = object()
        blocked = Blocker(None)
        packed = {"a": (live, blocked)}
        filtered = COMPAT.drop_optional_execution_blockers(
            DeclaredCollect(), packed, blocker_cls=Blocker
        )
        self.assertIs(filtered, packed)
        self.assertIs(filtered["a"][0], live)
        self.assertIs(filtered["a"][1], blocked)

    def test_input_is_list_mixed_sequence_blanks_blockers_and_keeps_live(self):
        class ListCollect(DeclaredCollect):
            INPUT_IS_LIST = True
            IGNORE_OPTIONAL_EXECUTION_BLOCKERS = True

        live0 = object()
        live1 = object()
        packed = {"a": [live0, Blocker(None), live1]}
        filtered = COMPAT.drop_optional_execution_blockers(
            ListCollect(), packed, blocker_cls=Blocker
        )
        self.assertEqual(len(filtered["a"]), 3)
        self.assertIs(filtered["a"][0], live0)
        self.assertIsNone(filtered["a"][1])
        self.assertIs(filtered["a"][2], live1)

    def test_patch_warns_and_is_fail_closed_when_execution_is_missing(self):
        sys.modules["execution"] = None
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", COMPAT.ThemeCollectHookWarning)
            status = COMPAT.patch_comfy_execution()
        self.assertEqual(status, "missing")
        self.assertTrue(
            any(isinstance(item.message, COMPAT.ThemeCollectHookWarning) for item in caught)
        )

    def test_incompatible_and_already_and_signature(self):
        fake = types.ModuleType("execution")
        calls = []

        async def original(*args, **kwargs):
            calls.append(("async", args, kwargs))
            return "ok-async"

        fake._async_map_node_over_list = original
        sys.modules["execution"] = fake
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", COMPAT.ThemeCollectHookWarning)
                self.assertEqual(COMPAT.patch_comfy_execution(), "applied")
                self.assertEqual(COMPAT.patch_comfy_execution(), "already")
            self.assertFalse(
                any(isinstance(item.message, COMPAT.ThemeCollectHookWarning) for item in caught)
            )

            live = object()
            blocked = Blocker(None)
            result = asyncio.run(
                fake._async_map_node_over_list(
                    "p",
                    "n",
                    DeclaredCollect(),
                    {"a": [live], "b": [blocked]},
                    "merge",
                    unexpected=True,
                )
            )
            self.assertEqual(result, "ok-async")
            # Future kwargs reached the original; filtered positional input.
            self.assertEqual(calls[0][1][3], {"a": [live]})
            self.assertTrue(calls[0][2].get("unexpected") is True)

            # Original TypeError is not swallowed.
            def boom(*args, **kwargs):
                raise TypeError("from original")

            # Replace the inner original through __wrapped__? The wrapper already
            # closed over `original`. Build a fresh module for this part.
        finally:
            sys.modules.pop("execution", None)

        fake2 = types.ModuleType("execution")

        def boom(*args, **kwargs):
            raise TypeError("from original")

        fake2._async_map_node_over_list = boom
        sys.modules["execution"] = fake2
        try:
            self.assertEqual(COMPAT.patch_comfy_execution(), "applied")
            with self.assertRaises(TypeError) as ctx:
                asyncio.run(
                    fake2._async_map_node_over_list(
                        "p", "n", DeclaredCollect(), {"a": [object()]}, "merge"
                    )
                )
            self.assertEqual(str(ctx.exception), "from original")
        finally:
            sys.modules.pop("execution", None)

    def test_sync_original_is_awaited_only_when_awaitable(self):
        fake = types.ModuleType("execution")

        def sync_map(*args, **kwargs):
            return "ok-sync"

        fake._async_map_node_over_list = sync_map
        sys.modules["execution"] = fake
        try:
            self.assertEqual(COMPAT.patch_comfy_execution(), "applied")
            result = asyncio.run(
                fake._async_map_node_over_list(
                    "p", "n", DeclaredCollect(), {"a": [object()]}, "merge"
                )
            )
            self.assertEqual(result, "ok-sync")
        finally:
            sys.modules.pop("execution", None)

    def test_incompatible_warns(self):
        fake = types.ModuleType("execution")
        fake._async_map_node_over_list = "not-callable"
        sys.modules["execution"] = fake
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", COMPAT.ThemeCollectHookWarning)
                status = COMPAT.patch_comfy_execution()
            self.assertEqual(status, "incompatible")
            self.assertTrue(
                any(isinstance(item.message, COMPAT.ThemeCollectHookWarning) for item in caught)
            )
        finally:
            sys.modules.pop("execution", None)

    def test_foreign_wrap_then_reload_does_not_stack(self):
        fake = types.ModuleType("execution")
        calls = []

        async def original(prompt_id, unique_id, obj, input_data_all, func, **kwargs):
            calls.append(("original", dict(input_data_all)))
            return "ok"

        fake._async_map_node_over_list = original
        sys.modules["execution"] = fake
        try:
            self.assertEqual(COMPAT.patch_comfy_execution(), "applied")
            s1_wrap = fake._async_map_node_over_list

            async def foreign(prompt_id, unique_id, obj, input_data_all, func, **kwargs):
                calls.append(("foreign", dict(input_data_all)))
                return await s1_wrap(
                    prompt_id, unique_id, obj, input_data_all, func, **kwargs
                )

            foreign.__wrapped__ = s1_wrap
            fake._async_map_node_over_list = foreign
            # Reload-style re-patch: hook still in the __wrapped__ chain.
            self.assertEqual(COMPAT.patch_comfy_execution(), "already")
            self.assertIs(fake._async_map_node_over_list, foreign)

            live = object()
            asyncio.run(
                fake._async_map_node_over_list(
                    "p",
                    "n",
                    DeclaredCollect(),
                    {"a": [live], "b": [Blocker(None)]},
                    "merge",
                )
            )
            self.assertEqual([name for name, _ in calls], ["foreign", "original"])
            self.assertEqual(list(calls[1][1].keys()), ["a"])
        finally:
            sys.modules.pop("execution", None)

    def test_displaced_hook_warns_and_does_not_stack(self):
        fake = types.ModuleType("execution")

        async def original(*args, **kwargs):
            return "ok"

        fake._async_map_node_over_list = original
        sys.modules["execution"] = fake
        try:
            self.assertEqual(COMPAT.patch_comfy_execution(), "applied")

            async def displaced(*args, **kwargs):
                return "foreign-only"

            # Foreign replacement with no __wrapped__ back to S1; mark remains.
            fake._async_map_node_over_list = displaced
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", COMPAT.ThemeCollectHookWarning)
                status = COMPAT.patch_comfy_execution()
            self.assertEqual(status, "displaced")
            self.assertIs(fake._async_map_node_over_list, displaced)
            self.assertTrue(
                any(isinstance(item.message, COMPAT.ThemeCollectHookWarning) for item in caught)
            )
        finally:
            sys.modules.pop("execution", None)

    def test_kwarg_layout_is_filtered(self):
        fake = types.ModuleType("execution")
        seen = {}

        async def original(*args, **kwargs):
            seen["kwargs"] = dict(kwargs)
            return "ok"

        fake._async_map_node_over_list = original
        sys.modules["execution"] = fake
        try:
            COMPAT.patch_comfy_execution()
            live = object()
            asyncio.run(
                fake._async_map_node_over_list(
                    obj=DeclaredCollect(),
                    input_data_all={"a": [live], "b": [Blocker(None)]},
                    prompt_id="p",
                    unique_id="n",
                    func="merge",
                )
            )
            self.assertEqual(list(seen["kwargs"]["input_data_all"].keys()), ["a"])
        finally:
            sys.modules.pop("execution", None)


if __name__ == "__main__":
    unittest.main()
