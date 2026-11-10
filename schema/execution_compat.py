"""Let opted-in nodes see optional ExecutionBlocker inputs instead of being skipped.

ComfyUI 0.44.0 ``execution._async_map_node_over_list`` (process_inputs,
around lines 269-318) treats *any* ``ExecutionBlocker`` in ``input_data_all``
as a reason to skip the node and propagate the blocker. It does not
distinguish required from optional sockets.

Theme Collect's ``a`` / ``b`` are optional and must ignore a blocked sibling
so a selected option can reach LoRA Aggregate. Set
``IGNORE_OPTIONAL_EXECUTION_BLOCKERS = True`` on a node class. This module
drops those optional blocker values (same as an unconnected socket) before
the stock short-circuit runs.

Required-input blockers are left untouched, so an unselected option slot
wired into a required input still skips that downstream node.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .blocker import is_execution_blocker

_HOOK_ATTR = "_s1_optional_blocker_filter"


def _node_flag(obj: Any) -> bool:
    if obj is None:
        return False
    if bool(getattr(obj, "IGNORE_OPTIONAL_EXECUTION_BLOCKERS", False)):
        return True
    cls = obj if isinstance(obj, type) else type(obj)
    return bool(getattr(cls, "IGNORE_OPTIONAL_EXECUTION_BLOCKERS", False))


def _optional_input_names(obj: Any) -> set[str]:
    cls = obj if isinstance(obj, type) else type(obj)
    getter = getattr(cls, "INPUT_TYPES", None)
    if getter is None:
        return set()
    types = getter() if isinstance(getter, type(lambda: None)) or callable(getter) else getter
    if not isinstance(types, Mapping):
        return set()
    optional = types.get("optional") or {}
    return set(optional.keys()) if isinstance(optional, Mapping) else set()


def _comfy_blocker_class() -> type | None:
    try:
        from comfy_execution.graph_utils import ExecutionBlocker as ComfyExecutionBlocker
    except ImportError:
        return None
    return ComfyExecutionBlocker


def _is_blocker_value(value: Any, blocker_cls: type | None) -> bool:
    if is_execution_blocker(value):
        return True
    if blocker_cls is not None and isinstance(value, blocker_cls):
        return True
    return False


def _entry_is_optional_blocker(value: Any, blocker_cls: type | None) -> bool:
    if _is_blocker_value(value, blocker_cls):
        return True
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) == 0:
            return False
        return any(_is_blocker_value(item, blocker_cls) for item in value)
    return False


def drop_optional_execution_blockers(
    obj: Any,
    input_data_all: Mapping[str, Any] | None,
    *,
    blocker_cls: type | None = None,
) -> dict[str, Any] | Mapping[str, Any] | None:
    """Return inputs with opted-in optional blockers removed.

    If ``obj`` does not opt in, ``input_data_all`` is returned unchanged.
    """

    if not input_data_all or not _node_flag(obj):
        return input_data_all
    if blocker_cls is None:
        blocker_cls = _comfy_blocker_class()
    optional = _optional_input_names(obj)
    if not optional:
        return input_data_all
    filtered: dict[str, Any] = {}
    changed = False
    for key, value in input_data_all.items():
        if key in optional and _entry_is_optional_blocker(value, blocker_cls):
            changed = True
            continue
        filtered[key] = value
    return filtered if changed else input_data_all


def patch_comfy_execution() -> str:
    """Wrap ComfyUI's map function if it is importable.

    Returns ``applied``, ``already``, ``missing``, or ``incompatible``.
    """

    try:
        import execution as exe
    except ImportError:
        return "missing"
    original = getattr(exe, "_async_map_node_over_list", None)
    if original is None or not callable(original):
        return "incompatible"
    if getattr(original, _HOOK_ATTR, False):
        return "already"

    async def wrapped(
        prompt_id,
        unique_id,
        obj,
        input_data_all,
        func,
        allow_interrupt=False,
        execution_block_cb=None,
        pre_execute_cb=None,
        v3_data=None,
    ):
        filtered = drop_optional_execution_blockers(obj, input_data_all)
        return await original(
            prompt_id,
            unique_id,
            obj,
            filtered,
            func,
            allow_interrupt=allow_interrupt,
            execution_block_cb=execution_block_cb,
            pre_execute_cb=pre_execute_cb,
            v3_data=v3_data,
        )

    setattr(wrapped, _HOOK_ATTR, True)
    wrapped.__wrapped__ = original
    exe._async_map_node_over_list = wrapped
    return "applied"


__all__ = [
    "drop_optional_execution_blockers",
    "patch_comfy_execution",
]
