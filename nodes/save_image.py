"""S1 Save Image (Scrubbed): core SaveImage with SystemOne secrets removed.

Mirrors ``SaveImage`` in ComfyUI v0.44.0 ``nodes.py``: same inputs, output
folder, ``get_save_image_path`` counter naming, ``compress_level`` 4, UI
preview result, ``args.disable_metadata``, and an ``IMAGE`` passthrough.
Before metadata is written, ``schema.scrub`` clears ``S1Settings.api_key``
and ``S1Settings.endpoint`` from deep copies of ``prompt`` and
``extra_pnginfo``. After each file is written its text chunks are read back;
if a scrubbed value is still there, every file written by this call is
deleted and the node raises.
"""

from __future__ import annotations

import json
import os

from ..schema.scrub import scrub_metadata, verify_png_scrubbed

CATEGORY = "SystemOne/LoraRouter"

try:  # ComfyUI runtime; tests replace these module attributes.
    import folder_paths  # type: ignore
except Exception:  # pragma: no cover - outside ComfyUI
    folder_paths = None

try:
    from comfy.cli_args import args  # type: ignore
except Exception:  # pragma: no cover - outside ComfyUI
    args = None


def _metadata_disabled() -> bool:
    return bool(getattr(args, "disable_metadata", False))


class S1SaveImageScrubbed:
    """Save images like core SaveImage, without the SystemOne key or URL."""

    def __init__(self):
        if folder_paths is None:
            raise RuntimeError("folder_paths is not available outside ComfyUI")
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"
        self.prefix_append = ""
        self.compress_level = 4

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "The images to save."}),
                "filename_prefix": (
                    "STRING",
                    {
                        "default": "ComfyUI",
                        "tooltip": (
                            "The prefix for the file to save. This may include formatting "
                            "information such as %date:yyyy-MM-dd% or %Empty Latent Image.width% "
                            "to include values from nodes."
                        ),
                    },
                ),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "save_images"
    OUTPUT_NODE = True
    CATEGORY = CATEGORY
    DESCRIPTION = (
        "Saves the input images to your ComfyUI output directory, like Save Image. "
        "The PNG still embeds prompt and workflow, but SystemOne Settings api_key and "
        "endpoint are cleared first (also where they appear through a linked String or "
        "Primitive node). The file is re-read after writing; if a cleared value is still "
        "present, the file is deleted and the node fails."
    )

    def save_images(self, images, filename_prefix="ComfyUI", prompt=None, extra_pnginfo=None):
        import numpy as np
        from PIL import Image
        from PIL.PngImagePlugin import PngInfo

        filename_prefix += self.prefix_append
        full_output_folder, filename, counter, subfolder, filename_prefix = folder_paths.get_save_image_path(
            filename_prefix, self.output_dir, images[0].shape[1], images[0].shape[0]
        )
        disabled = _metadata_disabled()
        values: set[str] = set()
        clean_prompt = clean_extra = None
        if not disabled:
            clean_prompt, clean_extra, values = scrub_metadata(prompt, extra_pnginfo)
        results = list()
        written: list[str] = []
        for batch_number, image in enumerate(images):
            i = 255.0 * image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
            metadata = None
            if not disabled:
                metadata = PngInfo()
                if clean_prompt is not None:
                    metadata.add_text("prompt", json.dumps(clean_prompt))
                if clean_extra is not None:
                    for x in clean_extra:
                        metadata.add_text(x, json.dumps(clean_extra[x]))

            filename_with_batch_num = filename.replace("%batch_num%", str(batch_number))
            file = f"{filename_with_batch_num}_{counter:05}_.png"
            path = os.path.join(full_output_folder, file)
            img.save(path, pnginfo=metadata, compress_level=self.compress_level)
            written.append(path)
            try:
                verify_png_scrubbed(path, values)
            except Exception:
                for item in written:
                    try:
                        os.remove(item)
                    except OSError:
                        pass
                raise
            results.append({"filename": file, "subfolder": subfolder, "type": self.type})
            counter += 1

        return {"ui": {"images": results}, "result": (images,)}
