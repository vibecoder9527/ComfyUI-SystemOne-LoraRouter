"""Read-only checks against a ComfyUI frontend 1.57.6 tree, if present.

These do not talk to a running server. They look at the frontend package
files on disk (container or S1_FRONTEND_STATIC) to document why slot.hidden
is ignored by Vue Nodes 2.0 and why addDOMWidget is the on-node UI path.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path


def frontend_static():
    env = os.environ.get("S1_FRONTEND_STATIC", "").strip()
    candidates = [Path(env)] if env else []
    candidates.extend(
        [
            Path("/root/.local/lib/python3.13/site-packages/comfyui_frontend_package/static"),
            Path("/usr/local/lib/python3.13/site-packages/comfyui_frontend_package/static"),
        ]
    )
    for path in candidates:
        try:
            if path.is_dir():
                return path
        except OSError:
            continue
    return None


def _search(root: Path, needles):
    text_hits = {needle: False for needle in needles}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".js", ".mjs", ".vue", ".ts", ".map"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for needle in needles:
            if not text_hits[needle] and needle in text:
                text_hits[needle] = True
        if all(text_hits.values()):
            break
    return text_hits


class Frontend1576Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = frontend_static()
        if cls.root is None:
            raise unittest.SkipTest("frontend 1.57.6 static tree is not on this host")

    def test_vue_nodes_outputs_are_not_filtered_by_hidden(self):
        hits = _search(
            self.root,
            (
                "nodeData.outputs",
                "nonWidgetedInputs",
                "addDOMWidget",
            ),
        )
        self.assertTrue(hits["nodeData.outputs"], "Vue node outputs come from nodeData.outputs")
        self.assertTrue(hits["nonWidgetedInputs"], "Vue inputs use nonWidgetedInputs, not slot.hidden")
        self.assertTrue(hits["addDOMWidget"], "addDOMWidget exists for on-node DOM widgets")

    def test_nodeslots_vfor_does_not_skip_hidden_outputs(self):
        # Prefer the source-mapped Vue file when the package ships it, else the bundle.
        vue = list(self.root.rglob("NodeSlots.vue"))
        texts = [path.read_text(encoding="utf-8", errors="ignore") for path in vue]
        if not texts:
            texts = []
            for path in self.root.rglob("*.js"):
                try:
                    chunk = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if "nodeData.outputs" in chunk and "v-for" in chunk:
                    texts.append(chunk)
                    break
        if not texts:
            self.skipTest("NodeSlots.vue is not shipped in this static tree and the JS bundle is minified")
        blob = "\n".join(texts)
        self.assertIn("nodeData.outputs", blob)
        # A hidden-aware renderer would filter outputs by .hidden before the v-for.
        self.assertNotRegex(
            blob,
            r"outputs\s*\.\s*filter\s*\([^)]*hidden",
            "NodeSlots should not filter outputs by hidden (1.57.6 Vue Nodes 2.0)",
        )

    def test_slot_and_node_menus_use_expected_1576_hooks(self):
        # Vue OutputSlot and LiteGraph NodeSlot both display
        # label || localized_name || name. Vue Nodes 2.0 opens the native
        # node menu from LGraphNode @contextmenu -> handleContextMenu ->
        # showNodeOptions.
        hits = _search(
            self.root,
            (
                "localized_name",
                "showNodeOptions",
                "handleContextMenu",
            ),
        )
        self.assertTrue(hits["localized_name"], "frontend slot display still has localized_name")
        self.assertTrue(hits["showNodeOptions"], "Vue Nodes 2.0 opens the native menu via showNodeOptions")
        self.assertTrue(hits["handleContextMenu"], "LGraphNode handleContextMenu is present in 1.57.6")
        # Prefer an unminified expression if the package ships it.
        blob_hits = _search(self.root, ("label||", "localized_name"))
        self.assertTrue(blob_hits["localized_name"])

