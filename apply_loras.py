"""Apply the aggregated LoRA list to MODEL and optional CLIP.

SPEC §4.3:

- When ``comfy.sd.load_lora_for_models`` imports, call it. ``clip`` may be None
  (``load_lora_for_models(model, None, ...)``). CLIP out stays None when the
  input clip was None.
- When ComfyUI is not importable, no-op and record a debug note. That is the
  offline fallback, not a missing-file error, so ``on_error`` does not raise.
- When ComfyUI is available and a file is missing or fails to load:
  ``passthrough`` skips that LoRA and records an error; ``raise`` raises
  ``ApplyError`` and stops the loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

APPLY_UNAVAILABLE_NOTE = (
    "ComfyUI APIs unavailable: apply_loras did not patch weights because "
    "comfy.sd.load_lora_for_models is not importable. MODEL and CLIP are unchanged."
)


class ApplyError(RuntimeError):
    """A LoRA file was missing or failed to load and ``on_error`` is ``raise``."""


@dataclass
class ApplyOutcome:
    model: Any
    clip: Any
    applied: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def apply_loras(
    model: Any,
    clip: Any,
    selected: list[dict[str, Any]],
    on_error: str = "passthrough",
) -> ApplyOutcome:
    """Patch `selected` onto `model` / `clip`, or no-op outside ComfyUI.

    `selected` items use the report shape: ``lora_id``, ``name``,
    ``strength_model``, ``strength_clip``, ``sources``. Order is preserved
    (the runner sorts by ``lora_id`` first).
    """

    outcome = ApplyOutcome(model=model, clip=clip)
    if not selected:
        outcome.notes.append("No LoRAs were selected.")
        return outcome

    api, import_error = _import_comfy()
    if api is None:
        detail = f"{type(import_error).__name__}: {import_error}" if import_error else "import failed"
        outcome.notes.append(f"{APPLY_UNAVAILABLE_NOTE} ({detail})")
        for item in selected:
            outcome.applied.append(_record(item, loaded=False))
        return outcome

    load_lora_for_models, load_torch_file, get_full_path = api
    for item in selected:
        lora_id = item["lora_id"]
        name = item["name"]
        try:
            lora_path = get_full_path("loras", name)
            if not lora_path:
                raise ApplyError(
                    f"LoRA file {name!r} (lora_id {lora_id!r}) was not found under ComfyUI loras/"
                )
            lora_object = _load_torch(load_torch_file, lora_path)
            patched = load_lora_for_models(
                outcome.model,
                outcome.clip,
                lora_object,
                item["strength_model"],
                item["strength_clip"],
            )
            if not isinstance(patched, tuple) or len(patched) != 2:
                raise ApplyError(
                    f"load_lora_for_models returned an unexpected value for lora_id {lora_id!r}"
                )
            patched_model, patched_clip = patched
            outcome.model = patched_model
            # SPEC §2.3 / §4.3: CLIP out remains None when the input clip was None.
            outcome.clip = None if clip is None else patched_clip
            outcome.applied.append(_record(item, loaded=True))
        except ApplyError as exc:
            _handle_lora_error(outcome, item, on_error, str(exc))
        except Exception as exc:
            _handle_lora_error(
                outcome,
                item,
                on_error,
                f"failed to apply lora_id {lora_id!r} ({name}): {type(exc).__name__}: {exc}",
            )
    if any(item["loaded"] for item in outcome.applied):
        count = sum(1 for item in outcome.applied if item["loaded"])
        outcome.notes.append(f"Patched {count} LoRA(s) onto MODEL.")
    return outcome


def _handle_lora_error(
    outcome: ApplyOutcome,
    item: dict[str, Any],
    on_error: str,
    message: str,
) -> None:
    # passthrough skips this file and keeps going. raise stops the graph.
    if on_error == "raise":
        raise ApplyError(message)
    outcome.errors.append(message)
    outcome.applied.append(_record(item, loaded=False))


def _record(item: dict[str, Any], *, loaded: bool) -> dict[str, Any]:
    record = {
        "lora_id": item["lora_id"],
        "name": item["name"],
        "strength_model": item["strength_model"],
        "strength_clip": item["strength_clip"],
        "sources": item["sources"],
        "loaded": loaded,
    }
    for key in ("slider", "weight_source", "warnings"):
        if key in item:
            record[key] = item[key]
    return record


def _import_comfy():
    try:
        import folder_paths
        import comfy.utils
        from comfy.sd import load_lora_for_models
    except Exception as exc:
        return None, exc
    return (load_lora_for_models, comfy.utils.load_torch_file, folder_paths.get_full_path), None


def _load_torch(load_torch_file, lora_path: str):
    try:
        return load_torch_file(lora_path, safe_load=True)
    except TypeError:
        # Older ComfyUI builds do not take safe_load.
        return load_torch_file(lora_path)
