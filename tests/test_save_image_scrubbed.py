"""S1 Save Image (Scrubbed): SystemOne api_key / endpoint never reach the PNG."""

from __future__ import annotations

import copy
import importlib
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.harness import PACKAGE_NAME, PKG

SCRUB = importlib.import_module(PACKAGE_NAME + ".schema.scrub")
SAVE = importlib.import_module(PACKAGE_NAME + ".nodes.save_image")

try:
    import numpy as np
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo
except Exception:  # pragma: no cover
    np = None

# Test-only fake values. They are not real credentials.
KEY = "sk-test-0123456789abcdef"
URL = "https://private.example.invalid/v1/systemone"
PRIM_KEY = "sk-prim-ZYXWVUTSRQ"
WF_PRIM_KEY = "sk-wfprim-424242"


def settings_inputs(api_key=KEY, endpoint=URL):
    return {
        "api_key": api_key,
        "api_model": "sys-1",
        "endpoint": endpoint,
        "noul_threshold": 0.5,
        "on_error": "passthrough",
        "min_confidence": 0.0,
    }


def make_prompt():
    return {
        "85": {"class_type": "S1Settings", "inputs": settings_inputs(), "_meta": {"title": "SystemOne Settings"}},
        "60": {"class_type": "CLIPTextEncode", "inputs": {"text": "a girl at the beach", "clip": ["4", 1]}},
        "86": {"class_type": "S1ThemeRoot", "inputs": {"theme_json": "{}", "positive": ["60", 0], "settings": ["85", 0]}},
        "9": {"class_type": "S1SaveImageScrubbed", "inputs": {"filename_prefix": "ComfyUI", "images": ["8", 0]}},
    }


def settings_wf_node(node_id=85, key=KEY, url=URL, inputs=None):
    return {
        "id": node_id,
        "type": "S1Settings",
        "inputs": inputs or [],
        "outputs": [{"name": "settings", "type": "S1_SETTINGS", "links": [1]}],
        "widgets_values": [key, "sys-1", url, 0.5, "passthrough", 0.0],
    }


def make_workflow():
    return {
        "last_node_id": 90,
        "nodes": [
            settings_wf_node(),
            {"id": 60, "type": "CLIPTextEncode", "widgets_values": ["a girl at the beach"]},
            {"id": 70, "type": "Note", "widgets_values": ["remember: endpoint is " + URL]},
        ],
        "links": [[1, 85, 0, 86, 2, "S1_SETTINGS"]],
        "extra": {"ds": {"scale": 1.0, "offset": [0, 0]}},
        "version": 0.4,
    }


class FakeImage:
    def __init__(self, height=8, width=12):
        self._array = np.full((height, width, 3), 0.5, dtype=np.float32)
        self.shape = self._array.shape

    def cpu(self):
        return self

    def numpy(self):
        return self._array


class FakeFolderPaths:
    def __init__(self, root):
        self.root = root

    def get_output_directory(self):
        return self.root

    def get_save_image_path(self, filename_prefix, output_dir, image_width=0, image_height=0):
        subfolder = os.path.dirname(os.path.normpath(filename_prefix))
        filename = os.path.basename(os.path.normpath(filename_prefix))
        folder = os.path.join(output_dir, subfolder)
        os.makedirs(folder, exist_ok=True)
        counter = 1
        for name in os.listdir(folder):
            if name.startswith(filename + "_") and name.endswith("_.png"):
                try:
                    counter = max(counter, int(name[len(filename) + 1 :].split("_")[0]) + 1)
                except ValueError:
                    pass
        return folder, filename, counter, subfolder, filename_prefix


def deep_contains(data, needle):
    return needle in json.dumps(data, ensure_ascii=False)


class LayoutTests(unittest.TestCase):
    def test_settings_widget_indices(self):
        self.assertEqual(SCRUB.settings_widget_indices(), {"api_key": 0, "endpoint": 2})
        self.assertEqual(SCRUB.SCRUB_FIELDS, ("api_key", "endpoint"))

    def test_layout_counts_control_slots_and_skips_socket_inputs(self):
        layout = SCRUB.widget_value_layout(
            {
                "required": {
                    "model": ("MODEL",),
                    "seed": ("INT", {"default": 0}),
                    "steps": ("INT", {"default": 20, "control_after_generate": True}),
                    "text": ("STRING", {"forceInput": True}),
                    "mode": (["a", "b"],),
                },
                "optional": {"note": ("STRING", {"default": ""})},
            }
        )
        self.assertEqual(layout, ["seed", "", "steps", "", "mode", "note"])


class ScrubTests(unittest.TestCase):
    def test_prompt_fields_cleared_link_left_and_live_untouched(self):
        prompt = make_prompt()
        prompt["85"]["inputs"]["endpoint"] = ["99", 0]
        live = copy.deepcopy(prompt)
        out = SCRUB.scrub_prompt(prompt)
        self.assertEqual(prompt, live, "live prompt not mutated")
        self.assertEqual(out["85"]["inputs"]["api_key"], "")
        self.assertEqual(out["85"]["inputs"]["endpoint"], ["99", 0], "link array left alone")
        for name in ("api_model", "noul_threshold", "on_error", "min_confidence"):
            self.assertEqual(out["85"]["inputs"][name], prompt["85"]["inputs"][name])
        self.assertEqual(out["60"], prompt["60"])

    def test_workflow_positional_dict_and_nested_subgraphs(self):
        inner = {"id": "sg-inner", "nodes": [settings_wf_node(3, key="sk-inner-999999", url="https://inner.invalid/x")], "links": []}
        outer = {
            "id": "sg-outer",
            "nodes": [settings_wf_node(2, key="sk-outer-888888", url="https://outer.invalid/x")],
            "links": [],
            "definitions": {"subgraphs": [inner]},
        }
        workflow = make_workflow()
        workflow["nodes"].append({"id": 40, "type": "S1Settings", "widgets_values": {"api_key": "sk-dict-777777", "api_model": "m", "endpoint": "https://dict.invalid/x"}})
        workflow["definitions"] = {"subgraphs": [outer]}
        live = copy.deepcopy(workflow)
        out = SCRUB.scrub_workflow(workflow)
        self.assertEqual(workflow, live)
        self.assertEqual(out["nodes"][0]["widgets_values"], ["", "sys-1", "", 0.5, "passthrough", 0.0])
        self.assertEqual(out["nodes"][3]["widgets_values"], {"api_key": "", "api_model": "m", "endpoint": ""})
        sub = out["definitions"]["subgraphs"][0]
        self.assertEqual(sub["nodes"][0]["widgets_values"][0], "")
        self.assertEqual(sub["nodes"][0]["widgets_values"][2], "")
        nested = sub["definitions"]["subgraphs"][0]["nodes"][0]["widgets_values"]
        self.assertEqual(nested, ["", "sys-1", "", 0.5, "passthrough", 0.0])
        values = SCRUB.collect_secret_values({}, workflow)
        self.assertTrue({"sk-outer-888888", "sk-inner-999999", "sk-dict-777777", "https://inner.invalid/x"} <= values)

    def test_short_widgets_list_is_not_indexed_past_its_end(self):
        workflow = {"nodes": [{"id": 1, "type": "S1Settings", "widgets_values": ["sk-only-key-1"]}]}
        out = SCRUB.scrub_workflow(workflow)
        self.assertEqual(out["nodes"][0]["widgets_values"], [""])

    def test_values_through_primitive_and_string_links(self):
        prompt = make_prompt()
        prompt["85"]["inputs"]["api_key"] = ["12", 0]
        prompt["85"]["inputs"]["endpoint"] = ["14", 0]
        prompt["12"] = {"class_type": "PrimitiveString", "inputs": {"value": PRIM_KEY}}
        prompt["14"] = {"class_type": "SomeStringPassthrough", "inputs": {"anything": ["15", 0]}}
        prompt["15"] = {"class_type": "String Literal", "inputs": {"string": URL}}
        workflow = make_workflow()
        workflow["nodes"][0]["inputs"] = [{"name": "api_key", "type": "STRING", "widget": {"name": "api_key"}, "link": 5}]
        workflow["nodes"][0]["widgets_values"][0] = "stale-value-should-go"
        workflow["nodes"].append({"id": 50, "type": "PrimitiveNode", "widgets_values": [WF_PRIM_KEY, "fixed"]})
        workflow["links"].append([5, 50, 0, 85, 0, "STRING"])
        extra = {"workflow": workflow, "other": {"comment": "uses " + PRIM_KEY}}
        live_prompt, live_extra = copy.deepcopy(prompt), copy.deepcopy(extra)
        new_prompt, new_extra, values = SCRUB.scrub_metadata(prompt, extra)
        self.assertEqual(prompt, live_prompt)
        self.assertEqual(extra, live_extra)
        self.assertTrue({PRIM_KEY, URL, WF_PRIM_KEY, "stale-value-should-go"} <= values)
        self.assertEqual(new_prompt["12"]["inputs"]["value"], "", "primitive source scrubbed")
        self.assertEqual(new_prompt["15"]["inputs"]["string"], "", "chained string source scrubbed")
        self.assertEqual(new_prompt["85"]["inputs"]["api_key"], ["12", 0], "links stay")
        for secret in (PRIM_KEY, URL, WF_PRIM_KEY, "stale-value-should-go"):
            self.assertFalse(deep_contains(new_prompt, secret))
            self.assertFalse(deep_contains(new_extra, secret))
        self.assertEqual(new_extra["workflow"]["nodes"][2]["widgets_values"], ["remember: endpoint is "])
        self.assertEqual(new_extra["workflow"]["nodes"][3]["widgets_values"], ["", "fixed"])
        self.assertEqual(new_extra["other"], {"comment": "uses "})

    def test_short_values_are_field_scrubbed_only(self):
        prompt = make_prompt()
        prompt["85"]["inputs"]["api_key"] = "abc"
        prompt["60"]["inputs"]["text"] = "abc def"
        new_prompt, _, values = SCRUB.scrub_metadata(prompt, None)
        self.assertIn("abc", values)
        self.assertEqual(new_prompt["85"]["inputs"]["api_key"], "")
        self.assertEqual(new_prompt["60"]["inputs"]["text"], "abc def", "short value not replaced elsewhere")
        empty = make_prompt()
        empty["85"]["inputs"]["api_key"] = ""
        _, _, values = SCRUB.scrub_metadata(empty, None)
        self.assertNotIn("", values)

    def test_everything_else_unchanged(self):
        prompt, extra = make_prompt(), {"workflow": make_workflow(), "foo": [1, {"bar": "baz"}]}
        new_prompt, new_extra, _ = SCRUB.scrub_metadata(prompt, extra)
        expected_prompt = copy.deepcopy(prompt)
        expected_prompt["85"]["inputs"]["api_key"] = ""
        expected_prompt["85"]["inputs"]["endpoint"] = ""
        self.assertEqual(new_prompt, expected_prompt)
        expected_wf = copy.deepcopy(extra["workflow"])
        expected_wf["nodes"][0]["widgets_values"][0] = ""
        expected_wf["nodes"][0]["widgets_values"][2] = ""
        expected_wf["nodes"][2]["widgets_values"] = ["remember: endpoint is "]
        self.assertEqual(new_extra["workflow"], expected_wf)
        self.assertEqual(new_extra["foo"], extra["foo"])


@unittest.skipIf(np is None, "numpy / PIL not installed")
class SaveNodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = FakeFolderPaths(self.tmp.name)
        patches = [
            mock.patch.object(SAVE, "folder_paths", self.folder),
            mock.patch.object(SAVE, "args", SimpleNamespace(disable_metadata=False)),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def files(self):
        return sorted(name for name in os.listdir(self.tmp.name) if name.endswith(".png"))

    def test_registered_like_core_save_image(self):
        cls = PKG.NODE_CLASS_MAPPINGS["S1SaveImageScrubbed"]
        self.assertIs(cls, SAVE.S1SaveImageScrubbed)
        self.assertEqual(PKG.NODE_DISPLAY_NAME_MAPPINGS["S1SaveImageScrubbed"], "S1 Save Image (Scrubbed)")
        spec = cls.INPUT_TYPES()
        self.assertEqual(list(spec["required"]), ["images", "filename_prefix"])
        self.assertEqual(spec["required"]["filename_prefix"][1]["default"], "ComfyUI")
        self.assertEqual(spec["hidden"], {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"})
        self.assertTrue(cls.OUTPUT_NODE)
        self.assertEqual(cls.RETURN_TYPES, ("IMAGE",))
        self.assertEqual(cls().compress_level, 4)

    def test_save_writes_scrubbed_png_and_keeps_metadata(self):
        prompt, extra = make_prompt(), {"workflow": make_workflow(), "custom": {"k": "v"}}
        live_prompt, live_extra = copy.deepcopy(prompt), copy.deepcopy(extra)
        images = [FakeImage(), FakeImage()]
        out = SAVE.S1SaveImageScrubbed().save_images(images, "sub/S1", prompt=prompt, extra_pnginfo=extra)
        self.assertEqual(prompt, live_prompt, "live prompt not mutated")
        self.assertEqual(extra, live_extra, "live extra_pnginfo not mutated")
        self.assertIs(out["result"][0], images)
        self.assertEqual(
            out["ui"]["images"],
            [
                {"filename": "S1_00001_.png", "subfolder": "sub", "type": "output"},
                {"filename": "S1_00002_.png", "subfolder": "sub", "type": "output"},
            ],
        )
        path = os.path.join(self.tmp.name, "sub", "S1_00001_.png")
        texts = SCRUB.png_text_chunks(path)
        self.assertEqual(set(texts), {"prompt", "workflow", "custom"})
        for text in texts.values():
            self.assertNotIn(KEY, text)
            self.assertNotIn(URL, text)
            self.assertNotIn(json.dumps(URL)[1:-1], text)
        saved_prompt = json.loads(texts["prompt"])
        self.assertEqual(saved_prompt["85"]["inputs"]["api_key"], "")
        self.assertEqual(saved_prompt["85"]["inputs"]["endpoint"], "")
        self.assertEqual(saved_prompt["85"]["inputs"]["api_model"], "sys-1")
        self.assertEqual(saved_prompt["60"], prompt["60"])
        saved_wf = json.loads(texts["workflow"])
        self.assertEqual(saved_wf["nodes"][0]["widgets_values"], ["", "sys-1", "", 0.5, "passthrough", 0.0])
        self.assertEqual(saved_wf["extra"], extra["workflow"]["extra"])
        self.assertEqual(json.loads(texts["custom"]), {"k": "v"})
        with Image.open(path) as img:
            self.assertEqual(img.size, (12, 8))
        again = SAVE.S1SaveImageScrubbed().save_images([FakeImage()], "sub/S1", prompt=prompt, extra_pnginfo=extra)
        self.assertEqual(again["ui"]["images"][0]["filename"], "S1_00003_.png", "counter continues")

    def test_forced_verification_failure_deletes_files_and_raises(self):
        prompt, extra = make_prompt(), {"workflow": make_workflow()}

        def leaky(p, e):
            values = SCRUB.collect_secret_values(p, e["workflow"])
            return copy.deepcopy(p), copy.deepcopy(e), values

        with mock.patch.object(SAVE, "scrub_metadata", side_effect=leaky):
            with self.assertRaises(SCRUB.ScrubVerificationError) as ctx:
                SAVE.S1SaveImageScrubbed().save_images([FakeImage(), FakeImage()], "S1", prompt=prompt, extra_pnginfo=extra)
        self.assertEqual(self.files(), [], "leaky file was deleted")
        self.assertNotIn(KEY, str(ctx.exception), "message never carries the secret")
        self.assertNotIn(URL, str(ctx.exception))

    def test_failure_on_second_image_deletes_the_first_too(self):
        prompt = make_prompt()
        calls = {"n": 0}
        real = SAVE.verify_png_scrubbed

        def flaky(path, values):
            calls["n"] += 1
            if calls["n"] == 2:
                raise SCRUB.ScrubVerificationError("forced")
            return real(path, values)

        with mock.patch.object(SAVE, "verify_png_scrubbed", side_effect=flaky):
            with self.assertRaises(SCRUB.ScrubVerificationError):
                SAVE.S1SaveImageScrubbed().save_images([FakeImage(), FakeImage()], "S1", prompt=prompt, extra_pnginfo=None)
        self.assertEqual(self.files(), [])

    def test_verify_reads_itxt_and_ztxt(self):
        path = os.path.join(self.tmp.name, "itxt.png")
        info = PngInfo()
        info.add_itxt("workflow", json.dumps({"k": KEY}), zip=True)
        Image.new("RGB", (2, 2)).save(path, pnginfo=info)
        with self.assertRaises(SCRUB.ScrubVerificationError):
            SCRUB.verify_png_scrubbed(path, {KEY})
        path2 = os.path.join(self.tmp.name, "ztxt.png")
        info2 = PngInfo()
        info2.add_text("prompt", json.dumps({"85": {"class_type": "S1Settings", "inputs": {"api_key": "xy"}}}), zip=True)
        Image.new("RGB", (2, 2)).save(path2, pnginfo=info2)
        with self.assertRaises(SCRUB.ScrubVerificationError):
            SCRUB.verify_png_scrubbed(path2, set())

    def test_disable_metadata_writes_no_text(self):
        prompt = make_prompt()
        with mock.patch.object(SAVE, "args", SimpleNamespace(disable_metadata=True)):
            with mock.patch.object(SAVE, "scrub_metadata") as scrub:
                out = SAVE.S1SaveImageScrubbed().save_images([FakeImage()], "S1", prompt=prompt, extra_pnginfo={"workflow": make_workflow()})
        scrub.assert_not_called()
        path = os.path.join(self.tmp.name, out["ui"]["images"][0]["filename"])
        self.assertEqual(SCRUB.png_text_chunks(path), {})

    def test_real_folder_paths_counter_naming_when_available(self):
        try:
            import folder_paths as real  # type: ignore
        except Exception:
            self.skipTest("ComfyUI folder_paths is not importable here")
        folder = FakeFolderPaths(self.tmp.name)
        folder.get_save_image_path = real.get_save_image_path
        with mock.patch.object(SAVE, "folder_paths", folder):
            first = SAVE.S1SaveImageScrubbed().save_images([FakeImage()], "S1real", prompt=make_prompt(), extra_pnginfo=None)
            second = SAVE.S1SaveImageScrubbed().save_images([FakeImage()], "S1real", prompt=make_prompt(), extra_pnginfo=None)
        self.assertEqual(first["ui"]["images"][0]["filename"], "S1real_00001_.png")
        self.assertEqual(second["ui"]["images"][0]["filename"], "S1real_00002_.png")


if __name__ == "__main__":
    unittest.main()
