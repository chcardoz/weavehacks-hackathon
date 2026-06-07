from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from typing import Any, TypeVar, overload

F = TypeVar("F", bound=Callable[..., Any])

_initialized: dict[str, bool] = {}


def init_tracing(project: str) -> bool:
    if project in _initialized:
        return _initialized[project]
    try:
        import weave

        weave.init(project)
        _initialized[project] = True
        return True
    except (ImportError, Exception):
        _initialized[project] = False
        return False


@overload
def traced(fn: F) -> F: ...
@overload
def traced(fn: None = ..., *, name: str | None = ...) -> Callable[[F], F]: ...


def traced(fn: F | None = None, *, name: str | None = None) -> F | Callable[[F], F]:
    def wrap(func: F) -> F:
        try:
            import weave

            if name is not None:
                return weave.op(name=name)(func)  # type: ignore[return-value]
            return weave.op(func)  # type: ignore[return-value]
        except (ImportError, Exception):
            return func

    if fn is not None:
        return wrap(fn)
    return wrap


@contextlib.contextmanager
def attributes(attrs: dict[str, Any]) -> Iterator[None]:
    try:
        import weave

        with weave.attributes(attrs):
            yield
    except (ImportError, Exception):
        with contextlib.nullcontext():
            yield


def current_trace_url() -> str | None:
    try:
        from weave.trace.context import call_context

        call = call_context.get_current_call()
        if call is None:
            return None
        return getattr(call, "ui_url", None)
    except Exception:
        return None
