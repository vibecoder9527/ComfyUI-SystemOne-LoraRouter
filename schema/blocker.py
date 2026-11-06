"""Execution skip sentinel for unselected option slots.

ComfyUI treats ``comfy_execution.graph_utils.ExecutionBlocker`` as a real
output value. A node that receives one on a required input is not run, and
the blocker propagates from that node. ``None`` as the message is silent.

This module returns ComfyUI's class when that package is importable, and a
local stand-in otherwise. Unittest in this repo does not import ComfyUI, so
it asserts the stand-in. A live graph skips only when the object ComfyUI
itself checks for is what the node returned.
"""

from __future__ import annotations

from typing import Any


class LocalExecutionBlocker:
    """Stand-in used when ComfyUI is not installed.

    ``message is None`` means a silent skip, matching ComfyUI.
    """

    def __init__(self, message: str | None) -> None:
        self.message = message

    def __repr__(self) -> str:
        return f"LocalExecutionBlocker({self.message!r})"


def execution_blocker(message: str | None = None) -> Any:
    """Return the blocker ComfyUI will honor, or the local stand-in."""

    try:
        from comfy_execution.graph_utils import ExecutionBlocker as ComfyExecutionBlocker
    except ImportError:
        return LocalExecutionBlocker(message)
    return ComfyExecutionBlocker(message)


def is_execution_blocker(value: Any) -> bool:
    """True for ComfyUI's blocker and for ``LocalExecutionBlocker``."""

    if isinstance(value, LocalExecutionBlocker):
        return True
    return type(value).__name__ == "ExecutionBlocker" and hasattr(value, "message")


__all__ = [
    "LocalExecutionBlocker",
    "execution_blocker",
    "is_execution_blocker",
]
