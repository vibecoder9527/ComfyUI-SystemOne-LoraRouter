"""Let opted-in nodes see optional ExecutionBlocker inputs instead of being skipped.

ComfyUI 0.44.0 ``execution._async_map_node_over_list`` (process_inputs,
around lines 269-318) treats *any* ``ExecutionBlocker`` in ``input_data_all``
as a reason to skip the node and propagate the blocker. It does not
distinguish required from optional sockets.

Theme Collect's ``a`` / ``b`` are optional and must ignore a blocked sibling
so a selected option can reach LoRA Aggregate. The opt-in flag
``IGNORE_OPTIONAL_EXECUTION_BLOCKERS = True`` must be declared on the node
*class itself* (not merely inherited). This module then sanitizes those
optional values before the stock short-circuit runs:

- A bare optional blocker, or a sequence of only blockers, is treated as
  unconnected (the key is omitted).
- A mixed optional sequence keeps live items in place and leaves blocked
  items as blockers, so the stock per-slice short-circuit skips only the
  blocked indices (no merge activation there) without dropping live
  neighbours or raising on those slices.
- For ``INPUT_IS_LIST`` nodes, blocked items in an optional list are
  replaced with ``None`` so the list-wide short-circuit cannot skip the
  whole call and drop live neighbours.
- Required-input blockers are left untouched, so an unselected option slot
  wired into a required input still skips that downstream node (or that
  batch slice).

The load-time wrapper around ``_async_map_node_over_list`` is fail-closed:
if it cannot be installed, Collect stays on stock behavior (a blocked
sibling skips the node). A visible warning is emitted. The hook is applied
at most once; if a later wrapper displaces it, this module warns and does
not stack another copy.
"""

from __future__ import annotations

import inspect
import logging
import warnings
from collections.abc import Mapping, Sequence
from typing import Any

from .blocker import is_execution_blocker

_HOOK_ATTR = "_s1_optional_blocker_filter"
_MODULE_MARK = "_s1_optional_blocker_filter_installed"
_LOGGER = logging.getLogger("ComfyUI-SystemOne-LoraRouter")

# 0.44 positional layout of _async_map_node_over_list.
_OBJ_INDEX = 2
_INPUT_INDEX = 3


class ThemeCollectHookWarning(UserWarning):
    """Visible warning when the Theme Collect executor hook cannot be used."""


def _node_flag(obj: Any) -> bool:
    """True only when the object's *own class* declares the opt-in flag.

    Subclasses do not inherit the behavior unless they set
    ``IGNORE_OPTIONAL_EXECUTION_BLOCKERS = True`` on their class body.
    An implicit inherit would also sanitize optional sockets a subclass
    adds, which may need to stay blocking.
    """

    if obj is None:
        return False
    cls = obj if isinstance(obj, type) else type(obj)
    return cls.__dict__.get("IGNORE_OPTIONAL_EXECUTION_BLOCKERS", False) is True


def _optional_input_names(obj: Any, input_data_all: Mapping[str, Any] | None = None) -> set[str]:
    """Optional socket names, including extra dynamic keys not in INPUT_TYPES.

    Required INPUT_TYPES keys stay required. Anything else present in
    ``input_data_all`` is treated as optional so a frontend-added Collect
    socket still gets the fail-closed optional-blocker filter.
    """

    cls = obj if isinstance(obj, type) else type(obj)
    getter = getattr(cls, "INPUT_TYPES", None)
    declared_optional: set[str] = set()
    required: set[str] = set()
    if getter is not None:
        types = getter() if callable(getter) else getter
        if isinstance(types, Mapping):
            optional = types.get("optional") or {}
            if isinstance(optional, Mapping):
                declared_optional = set(optional.keys())
            req = types.get("required") or {}
            if isinstance(req, Mapping):
                required = set(req.keys())
    extra = set()
    if input_data_all:
        extra = set(input_data_all.keys()) - required
    return declared_optional | extra


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


def _is_value_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _sanitize_optional_value(
    value: Any,
    blocker_cls: type | None,
    *,
    input_is_list: bool,
) -> tuple[bool, Any]:
    """Return ``(drop_key, new_value)`` for one optional input.

    ``drop_key`` True means treat the socket as unconnected. A mixed
    sequence keeps live items. In the default map-over-list path, blocked
    items stay blockers so only that slice is skipped. For
    ``INPUT_IS_LIST``, blocked items become ``None`` so a single list-wide
    short-circuit cannot drop live neighbours.
    """

    if _is_blocker_value(value, blocker_cls):
        return True, None
    if not _is_value_sequence(value):
        return False, value
    if len(value) == 0:
        return False, value
    out: list[Any] = []
    live = 0
    blocked = 0
    for item in value:
        if _is_blocker_value(item, blocker_cls):
            out.append(None if input_is_list else item)
            blocked += 1
        else:
            out.append(item)
            live += 1
    if live == 0:
        return True, None
    if blocked == 0:
        return False, value
    if not input_is_list:
        # Leave blockers in place; per-slice short-circuit handles them.
        return False, value
    if isinstance(value, tuple):
        return False, tuple(out)
    return False, out


def drop_optional_execution_blockers(
    obj: Any,
    input_data_all: Mapping[str, Any] | None,
    *,
    blocker_cls: type | None = None,
) -> dict[str, Any] | Mapping[str, Any] | None:
    """Return inputs with opted-in optional blockers sanitized.

    If ``obj`` does not opt in, ``input_data_all`` is returned unchanged.
    Required keys are never modified.
    """

    if not input_data_all or not _node_flag(obj):
        return input_data_all
    if blocker_cls is None:
        blocker_cls = _comfy_blocker_class()
    optional = _optional_input_names(obj, input_data_all)
    if not optional:
        return input_data_all
    input_is_list = bool(getattr(obj, "INPUT_IS_LIST", False))
    filtered: dict[str, Any] = {}
    changed = False
    for key, value in input_data_all.items():
        if key not in optional:
            filtered[key] = value
            continue
        drop, new_value = _sanitize_optional_value(
            value, blocker_cls, input_is_list=input_is_list
        )
        if drop:
            changed = True
            continue
        if new_value is not value:
            changed = True
        filtered[key] = new_value
    return filtered if changed else input_data_all


def _iter_wrap_chain(func: Any):
    seen: set[int] = set()
    current = func
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = getattr(current, "__wrapped__", None)


def hook_install_state(exe_module: Any, current: Any) -> str:
    """Return ``in_chain``, ``displaced``, or ``absent``."""

    in_chain = any(getattr(fn, _HOOK_ATTR, False) for fn in _iter_wrap_chain(current))
    marked = bool(getattr(exe_module, _MODULE_MARK, False))
    if in_chain:
        return "in_chain"
    if marked:
        return "displaced"
    return "absent"


def _extract_map_args(args: tuple, kwargs: dict) -> tuple[Any, Any, str] | None:
    """Locate ``obj`` and ``input_data_all`` from a future-compatible call.

    Returns ``(obj, input_data_all, loc)`` where ``loc`` is ``kw`` or
    ``pos``. ``None`` means the call does not match the 0.44 layout; the
    wrapper must pass the call through unfiltered (fail closed).
    """

    if "obj" in kwargs:
        obj = kwargs["obj"]
    elif len(args) > _OBJ_INDEX:
        obj = args[_OBJ_INDEX]
    else:
        return None
    if "input_data_all" in kwargs:
        return obj, kwargs["input_data_all"], "kw"
    if len(args) > _INPUT_INDEX:
        return obj, args[_INPUT_INDEX], "pos"
    return None


def _emit_hook_warning(status: str, detail: str = "") -> None:
    extra = f" {detail}" if detail else ""
    message = (
        "Theme Collect executor hook was not installed "
        f"(reason={status}).{extra} Optional ExecutionBlocker inputs will "
        "skip Theme Collect, so a selected sibling will not reach Aggregate. "
        "This is fail-closed; downstream generation will not run on a "
        "partially blocked Collect. Required-input blockers are unchanged."
    )
    warnings.warn(message, ThemeCollectHookWarning, stacklevel=3)
    _LOGGER.warning(message)


def patch_comfy_execution() -> str:
    """Wrap ComfyUI's map function if it is importable.

    Returns ``applied``, ``already``, ``missing``, ``incompatible``, or
    ``displaced``. Failure statuses emit ``ThemeCollectHookWarning`` and
    leave the stock short-circuit in place (fail closed).

    Stacking: a module mark plus the ``__wrapped__`` chain prevent a second
    install, including after this package reloads. Limitation: if a foreign
    wrapper replaces ``_async_map_node_over_list``, hides ``__wrapped__``,
    *and* clears the module mark, a later install could wrap again; that
    case cannot be detected robustly.
    """

    try:
        import execution as exe
    except ImportError:
        _emit_hook_warning("missing", "ComfyUI execution module is not importable.")
        return "missing"
    original = getattr(exe, "_async_map_node_over_list", None)
    if original is None or not callable(original):
        _emit_hook_warning(
            "incompatible",
            "execution._async_map_node_over_list is missing or not callable.",
        )
        return "incompatible"
    state = hook_install_state(exe, original)
    if state == "in_chain":
        setattr(exe, _MODULE_MARK, True)
        return "already"
    if state == "displaced":
        _emit_hook_warning(
            "displaced",
            "A later wrapper replaced execution._async_map_node_over_list "
            "and this hook is no longer in the callable chain. Another "
            "copy will not be stacked.",
        )
        return "displaced"

    async def wrapped(*args, **kwargs):
        extracted = _extract_map_args(args, kwargs)
        call_args = args
        call_kwargs = kwargs
        if extracted is not None:
            obj, input_data_all, loc = extracted
            filtered = drop_optional_execution_blockers(obj, input_data_all)
            if filtered is not input_data_all:
                if loc == "kw":
                    call_kwargs = dict(kwargs)
                    call_kwargs["input_data_all"] = filtered
                else:
                    args_list = list(args)
                    args_list[_INPUT_INDEX] = filtered
                    call_args = tuple(args_list)
        # Do not catch TypeError: errors from the original map must propagate.
        result = original(*call_args, **call_kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    setattr(wrapped, _HOOK_ATTR, True)
    wrapped.__wrapped__ = original
    wrapped.__name__ = getattr(original, "__name__", "wrapped")
    exe._async_map_node_over_list = wrapped
    setattr(exe, _MODULE_MARK, True)
    return "applied"


__all__ = [
    "ThemeCollectHookWarning",
    "drop_optional_execution_blockers",
    "hook_install_state",
    "patch_comfy_execution",
]
