"""Structured JSON logging with encounter-aware context.

Usage::

    from rcm_agent.observability import get_logger, setup_logging

    setup_logging()  # call once at app startup
    logger = get_logger(__name__)

    logger.info("Router classified encounter",
                encounter_id="ENC-001", stage="CODING", confidence=0.95)
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Protocol, cast

_SETUP_DONE = False


class StructuredLoggerProtocol(Protocol):
    """Protocol for structured loggers that accept extra keyword arguments."""

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None: ...
    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None: ...
    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None: ...
    def error(self, msg: str, *args: Any, **kwargs: Any) -> None: ...
    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None: ...


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "_extra", None)
        if extra:
            payload.update(extra)

        if record.exc_info and record.exc_info[1] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class _HumanFormatter(logging.Formatter):
    """Readable format with optional extra fields appended."""

    _FMT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

    def __init__(self) -> None:
        super().__init__(fmt=self._FMT, datefmt="%Y-%m-%d %H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extra = getattr(record, "_extra", None)
        if extra:
            parts = " ".join(f"{k}={v}" for k, v in extra.items())
            return f"{base} | {parts}"
        return base


class StructuredLogger(logging.Logger):
    """Logger subclass that threads extra keyword arguments into every record."""

    def _log(  # type: ignore[override]
        self,
        level: int,
        msg: object,
        args: Any,
        exc_info: Any = None,
        extra: dict[str, Any] | None = None,
        stack_info: bool = False,
        stacklevel: int = 1,
        **kwargs: Any,
    ) -> None:
        extra = extra or {}
        extra["_extra"] = kwargs
        super()._log(level, msg, args, exc_info=exc_info, extra=extra, stack_info=stack_info, stacklevel=stacklevel)


logging.setLoggerClass(StructuredLogger)


def setup_logging(
    *,
    level: str | None = None,
    fmt: str | None = None,
) -> None:
    """Configure root logging.  Safe to call multiple times (idempotent).

    Parameters
    ----------
    level : str, optional
        Log level name.  Defaults to ``RCM_AGENT_LOG_LEVEL`` env var, then ``INFO``.
    fmt : str, optional
        ``"json"`` for structured JSON lines, ``"human"`` for readable output.
        Defaults to ``RCM_AGENT_LOG_FORMAT`` env var, then ``"human"``.
    """
    global _SETUP_DONE
    if _SETUP_DONE:
        return
    _SETUP_DONE = True

    level = level or os.environ.get("RCM_AGENT_LOG_LEVEL", "INFO")
    fmt = fmt or os.environ.get("RCM_AGENT_LOG_FORMAT", "human")

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JsonFormatter() if fmt == "json" else _HumanFormatter())

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()
    root.addHandler(handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def reset_logging() -> None:
    """Allow ``setup_logging`` to be called again (for tests)."""
    global _SETUP_DONE
    _SETUP_DONE = False


def get_logger(name: str) -> StructuredLoggerProtocol:
    """Return a StructuredLogger bound to *name*."""
    return cast(StructuredLoggerProtocol, logging.getLogger(name))
