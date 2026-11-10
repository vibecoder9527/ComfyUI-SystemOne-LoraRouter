"""Isolated PromptExecutor tests for the hardened Theme Collect hook.

Uses ComfyUI 0.44 PromptExecutor in-process with stub decision/model/sink
nodes. Does not submit a prompt to a running server, load models, or call
SystemOne. This is scheduler evidence, not KSampler/Preview image
generation.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

# This repo also has a product `nodes/` package. Put ComfyUI first.
_COMFY_ROOT = Path(os.environ.get("COMFYUI_ROOT", "/root/ComfyUI"))
try:
    _comfy_present = _COMFY_ROOT.is_dir()
except OSError:
    _comfy_present = False
if _comfy_present:
    sys.path.insert(0, str(_COMFY_ROOT))

from tests.harness import (
    PKG,
    CountingClient,
    as_payload,
    option,
    run_theme,
    theme_doc,
)


def _comfy_available():
    try:
        import execution  # noqa: F401
        from comfy_execution.graph_utils import ExecutionBlocker  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(_comfy_available(), "ComfyUI execution module is not importable")
class CollectPromptExecutorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import execution
        import nodes

        if not hasattr(nodes, "NODE_CLASS_MAPPINGS"):
            raise RuntimeError("imported the wrong nodes module: %r" % (nodes,))
        from comfy_execution.graph_utils import ExecutionBlocker
        cls.execution = execution
        cls.nodes = nodes
        cls.ExecutionBlocker = ExecutionBlocker
        cls.Collect = PKG.NODE_CLASS_MAPPINGS["S1ThemeCollect"]

    def setUp(self):
        execution = self.execution
        nodes = self.nodes
        ExecutionBlocker = self.ExecutionBlocker
        Collect = self.Collect

        def payload(option_id, tags):
            result = run_theme(
                theme_json=theme_doc(
                    theme_id="theme_1",
                    options=[option(option_id, list(tags))],
                ),
                client=CountingClient(),
            ).result
            return as_payload(result, slot_option_id=option_id)

        self.payload_a = payload("option_1", ["bikini"])
        self.payload_b = payload("option_2", ["none"])

        class MutexRoot:
            calls = 0
            FUNCTION = "run"
            RETURN_TYPES = ("S1_DECISION", "S1_DECISION")

            @classmethod
            def INPUT_TYPES(cls):
                return {"required": {"select": (["a", "b", "none"],)}}

            def run(self, select):
                type(self).calls += 1
                a = self_outer.payload_a if select == "a" else ExecutionBlocker(None)
                b = self_outer.payload_b if select == "b" else ExecutionBlocker(None)
                if select == "both":
                    a = self_outer.payload_a
                    b = self_outer.payload_b
                return (a, b)

        self_outer = self

        class ModelStub:
            FUNCTION = "run"
            RETURN_TYPES = ("MODEL",)

            @classmethod
            def INPUT_TYPES(cls):
                return {"required": {}}

            def run(self):
                return ("stub-model",)

        class AggregateStub:
            calls = 0
            last_decision = None
            FUNCTION = "apply"
            RETURN_TYPES = ("MODEL",)

            @classmethod
            def INPUT_TYPES(cls):
                return {
                    "required": {
                        "model": ("MODEL",),
                        "decision": ("S1_DECISION",),
                    }
                }

            def apply(self, model, decision):
                type(self).calls += 1
                type(self).last_decision = decision
                return (model,)

        class Sink:
            calls = 0
            last = None
            FUNCTION = "run"
            RETURN_TYPES = ()
            OUTPUT_NODE = True

            @classmethod
            def INPUT_TYPES(cls):
                return {"required": {"model": ("MODEL",)}}

            def run(self, model):
                type(self).calls += 1
                type(self).last = model
                return ()

        class Probe:
            calls = 0
            FUNCTION = "run"
            RETURN_TYPES = ()
            OUTPUT_NODE = True

            @classmethod
            def INPUT_TYPES(cls):
                return {"required": {"value": ("S1_DECISION",)}}

            def run(self, value):
                type(self).calls += 1
                return ()

        MutexRoot.calls = 0
        AggregateStub.calls = 0
        AggregateStub.last_decision = None
        Sink.calls = 0
        Sink.last = None
        Probe.calls = 0
        self.MutexRoot = MutexRoot
        self.AggregateStub = AggregateStub
        self.Sink = Sink
        self.Probe = Probe

        mapping = {
            "S1MutexRootStub": MutexRoot,
            "S1ThemeCollect": Collect,
            "S1ModelStub": ModelStub,
            "S1AggregateStub": AggregateStub,
            "S1SinkStub": Sink,
            "S1ProbeStub": Probe,
        }
        self._orig = {}
        for name, cls in mapping.items():
            self._orig[name] = nodes.NODE_CLASS_MAPPINGS.get(name)
            nodes.NODE_CLASS_MAPPINGS[name] = cls

        self.cache_args = {"ram": 0, "ram_inactive": 0}
        self.CacheType = getattr(execution, "CacheType", None)

    def tearDown(self):
        for name, prev in self._orig.items():
            if prev is None:
                self.nodes.NODE_CLASS_MAPPINGS.pop(name, None)
            else:
                self.nodes.NODE_CLASS_MAPPINGS[name] = prev

    def _executor(self):
        server = SimpleNamespace(client_id=None, send_sync=Mock(), last_node_id=None)
        none = getattr(self.CacheType, "NONE", False) if self.CacheType is not None else False
        return self.execution.PromptExecutor(
            server, cache_type=none, cache_args=self.cache_args
        )

    def _graph(self, select, include_probe=True):
        prompt = {
            "root": {"class_type": "S1MutexRootStub", "inputs": {"select": select}},
            "collect": {
                "class_type": "S1ThemeCollect",
                "inputs": {"a": ["root", 0], "b": ["root", 1]},
            },
            "model": {"class_type": "S1ModelStub", "inputs": {}},
            "agg": {
                "class_type": "S1AggregateStub",
                "inputs": {"model": ["model", 0], "decision": ["collect", 0]},
            },
            "sink": {"class_type": "S1SinkStub", "inputs": {"model": ["agg", 0]}},
        }
        outputs = ["sink"]
        if include_probe and select in {"a", "b"}:
            slot = 1 if select == "a" else 0
            prompt["probe"] = {
                "class_type": "S1ProbeStub",
                "inputs": {"value": ["root", slot]},
            }
            outputs.append("probe")
        return prompt, outputs

    def _run(self, prompt, outputs):
        executor = self._executor()
        executor.execute(prompt, "s1-harden", execute_outputs=outputs)
        return executor

    def test_option_a_reaches_collect_aggregate_and_sink(self):
        prompt, outputs = self._graph("a")
        executor = self._run(prompt, outputs)
        self.assertTrue(executor.success)
        self.assertEqual(self.MutexRoot.calls, 1)
        self.assertEqual(self.AggregateStub.calls, 1)
        self.assertIs(self.AggregateStub.last_decision, self.payload_a)
        self.assertEqual(self.payload_a.slot_option_id, "option_1")
        self.assertEqual(self.payload_a.result.tags, ["bikini"])
        self.assertEqual(self.Sink.calls, 1)
        self.assertEqual(self.Sink.last, "stub-model")
        self.assertEqual(self.Probe.calls, 0)

    def test_option_b_reaches_collect_aggregate_and_sink(self):
        prompt, outputs = self._graph("b")
        executor = self._run(prompt, outputs)
        self.assertTrue(executor.success)
        self.assertEqual(self.AggregateStub.calls, 1)
        self.assertIs(self.AggregateStub.last_decision, self.payload_b)
        self.assertEqual(self.payload_b.slot_option_id, "option_2")
        self.assertEqual(self.Sink.calls, 1)
        self.assertEqual(self.Probe.calls, 0)

    def test_both_blocked_is_fail_closed_and_does_not_run_sink(self):
        prompt, outputs = self._graph("none", include_probe=False)
        prompt["probe_a"] = {
            "class_type": "S1ProbeStub",
            "inputs": {"value": ["root", 0]},
        }
        prompt["probe_b"] = {
            "class_type": "S1ProbeStub",
            "inputs": {"value": ["root", 1]},
        }
        executor = self._run(prompt, ["sink", "probe_a", "probe_b"])
        self.assertFalse(executor.success)
        self.assertEqual(self.AggregateStub.calls, 0)
        self.assertEqual(self.Sink.calls, 0)
        self.assertEqual(self.Probe.calls, 0)

    def test_required_blocker_still_blocks_and_nonselected_probe_does_not_run(self):
        # Isolated required consumer on the unselected slot, no Collect path.
        prompt = {
            "root": {"class_type": "S1MutexRootStub", "inputs": {"select": "a"}},
            "probe": {
                "class_type": "S1ProbeStub",
                "inputs": {"value": ["root", 1]},
            },
        }
        executor = self._run(prompt, ["probe"])
        self.assertEqual(self.MutexRoot.calls, 1)
        self.assertEqual(self.Probe.calls, 0)
        # Silent blocker typically still counts as success.
        self.assertEqual(self.AggregateStub.calls, 0)
        self.assertEqual(self.Sink.calls, 0)


if __name__ == "__main__":
    unittest.main()
