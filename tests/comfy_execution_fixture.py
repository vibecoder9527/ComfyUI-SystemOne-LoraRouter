"""Isolated ComfyUI 0.44.0 executor short-circuit for Theme Collect tests.

The stock loop is taken from ComfyUI v0.44.0 (tag, commit 2c75dc1b)
``execution.py`` ``_async_map_node_over_list.process_inputs`` (lines 266-318)
and the bare-blocker expansion in ``get_output_from_returns`` (lines 405-406).

This fixture is V1-only: it calls ``getattr(obj, func)(**inputs)`` or
propagates the blocker. It does not import torch or start a ComfyUI server.
When the real ``execution`` module is importable, tests also run against it.
"""

from __future__ import annotations

import asyncio
from typing import Any


class ExecutionBlocker:
    """Stand-in matching ``comfy_execution.graph_utils.ExecutionBlocker``."""

    def __init__(self, message):
        self.message = message

    def __repr__(self) -> str:
        return f"ExecutionBlocker({self.message!r})"


async def map_node_over_list_v044(
    prompt_id,
    unique_id,
    obj,
    input_data_all,
    func,
    allow_interrupt=False,
    execution_block_cb=None,
    pre_execute_cb=None,
    v3_data=None,
    *,
    blocker_cls: type = ExecutionBlocker,
):
    """Reproduce the 0.44 short-circuit for any ExecutionBlocker input."""

    input_is_list = getattr(obj, "INPUT_IS_LIST", False)
    if not input_data_all:
        max_len_input = 0
    else:
        max_len_input = max(len(x) for x in input_data_all.values())

    def slice_dict(d, i):
        return {k: v[i if len(v) > i else -1] for k, v in d.items()}

    results = []

    async def process_inputs(inputs, index=None, input_is_list=False):
        execution_block = None
        for k, v in inputs.items():
            if input_is_list:
                for e in v:
                    if isinstance(e, blocker_cls):
                        v = e
                        break
            if isinstance(v, blocker_cls):
                execution_block = execution_block_cb(v) if execution_block_cb else v
                break
        if execution_block is None:
            f = getattr(obj, func)
            if index is not None and pre_execute_cb is not None:
                pre_execute_cb(index)
            result = f(**inputs)
            results.append(result)
        else:
            results.append(execution_block)

    if input_is_list:
        await process_inputs(input_data_all, 0, input_is_list=input_is_list)
    elif max_len_input == 0:
        await process_inputs({})
    else:
        for i in range(max_len_input):
            input_dict = slice_dict(input_data_all, i)
            await process_inputs(input_dict, i)
    return results


def expand_return(return_values, obj, blocker_cls: type = ExecutionBlocker):
    """Expand a bare blocker to every return socket, as 0.44 does."""

    expanded = []
    for r in return_values:
        if isinstance(r, blocker_cls):
            r = tuple([r] * len(obj.RETURN_TYPES))
        expanded.append(r)
    return expanded


def run_map(obj, input_data_all, *, blocker_cls: type = ExecutionBlocker):
    return_values = asyncio.run(
        map_node_over_list_v044(
            "prompt",
            "node",
            obj,
            input_data_all,
            obj.FUNCTION,
            blocker_cls=blocker_cls,
        )
    )
    return expand_return(return_values, obj, blocker_cls=blocker_cls)


def try_import_real_execution() -> tuple[Any, Any] | None:
    """Return ``(execution_module, ExecutionBlocker)`` or None."""

    try:
        import execution as exe
        from comfy_execution.graph_utils import ExecutionBlocker as ComfyExecutionBlocker
    except ImportError:
        return None
    return exe, ComfyExecutionBlocker


__all__ = [
    "ExecutionBlocker",
    "expand_return",
    "map_node_over_list_v044",
    "run_map",
    "try_import_real_execution",
]
