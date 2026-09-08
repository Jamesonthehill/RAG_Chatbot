from __future__ import annotations

from contextvars import ContextVar, Token
import hashlib
import logging
import sys
from typing import Any

from app import settings


LOGGER = logging.getLogger("app.pipeline")
if not LOGGER.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False

_trace_id: ContextVar[str | None] = ContextVar("pipeline_trace_id", default=None)
_conversation_id: ContextVar[str | None] = ContextVar("pipeline_conversation_id", default=None)


def begin_trace(trace_id: str, conversation_id: str | None = None) -> tuple[Token, Token]:
    return _trace_id.set(trace_id), _conversation_id.set(conversation_id)


def end_trace(tokens: tuple[Token, Token]) -> None:
    trace_token, conversation_token = tokens
    _conversation_id.reset(conversation_token)
    _trace_id.reset(trace_token)


def set_conversation_id(conversation_id: str | None) -> None:
    _conversation_id.set(conversation_id)


def trace_active() -> bool:
    return _trace_id.get() is not None


def _field(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return str(value).lower()
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace(" ", "_")
    )


def log_event(stage: int | str, event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    trace_id = _trace_id.get()
    if not trace_id:
        return
    values = {
        "trace_id": trace_id,
        "conversation_id": _conversation_id.get(),
        "stage": stage,
        "event": event,
        **fields,
    }
    LOGGER.log(level, " ".join(f"{key}={_field(value)}" for key, value in values.items()))


def log_exception(stage: int | str, event: str, error: BaseException, **fields: Any) -> None:
    trace_id = _trace_id.get()
    if not trace_id:
        return
    values = {
        "trace_id": trace_id,
        "conversation_id": _conversation_id.get(),
        "stage": stage,
        "event": event,
        "error_type": type(error).__name__,
        **fields,
    }
    LOGGER.error(" ".join(f"{key}={_field(value)}" for key, value in values.items()))


def debug_digest(label: str, value: str) -> None:
    """Log a non-reversible content fingerprint only when explicitly enabled."""
    if not settings.DEBUG_PIPELINE_LOGS:
        return
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    log_event("debug", f"{label}_digest", chars=len(value), sha256=digest)
