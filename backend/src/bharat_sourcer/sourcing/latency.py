"""Request-local scheduling deadline; in-flight synchronous I/O may finish after it."""

import time
from contextlib import contextmanager
from contextvars import ContextVar

_deadline: ContextVar[float | None] = ContextVar("buyer_deadline", default=None)


def remaining() -> float:
    deadline = _deadline.get()
    return max(0.0, deadline - time.monotonic()) if deadline is not None else float("inf")


def allowed() -> bool:
    return remaining() > 0


@contextmanager
def limit(seconds: float):
    token = _deadline.set(time.monotonic() + min(seconds, remaining()))
    try:
        yield
    finally:
        _deadline.reset(token)
