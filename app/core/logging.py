"""Enhanced logging with structured logging support"""

from __future__ import annotations

import logging
import uuid
from collections import deque
from contextvars import ContextVar
from typing import Any, Deque, Dict, Optional

import structlog

# Legacy log buffer for backward compatibility
LOG_BUFFER: Deque[Dict[str, object]] = deque(maxlen=800)

# Correlation ID context
correlation_id_context: ContextVar[str] = ContextVar("correlation_id", default="")


class CorrelationContext:
    """Manages correlation IDs for request tracing"""

    @classmethod
    def get(cls) -> str:
        """Get current correlation ID or generate new one"""
        cid = correlation_id_context.get()
        if not cid:
            cid = str(uuid.uuid4())
            correlation_id_context.set(cid)
        return cid

    @classmethod
    def set(cls, correlation_id: str) -> None:
        """Set correlation ID for current context"""
        correlation_id_context.set(correlation_id)

    @classmethod
    def clear(cls) -> None:
        """Clear correlation ID"""
        correlation_id_context.set("")


def add_correlation_id(logger, method_name, event_dict):
    """Add correlation ID to log events"""
    event_dict["correlation_id"] = CorrelationContext.get()
    return event_dict


# Configure structlog
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        add_correlation_id,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)


class LogBufferHandler(logging.Handler):
    """Handler that stores logs in a buffer"""

    def __init__(self, buffer: Deque[Dict[str, object]]) -> None:
        super().__init__()
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        self._buffer.append(
            {
                "ts": int(record.created * 1000),
                "level": record.levelname,
                "message": message,
                "correlation_id": CorrelationContext.get(),
            }
        )


def setup_logger(name: str = "copy-sync") -> logging.Logger:
    """Setup standard Python logger with buffer handler"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(stream_handler)

    if not any(isinstance(h, LogBufferHandler) for h in logger.handlers):
        logger.addHandler(LogBufferHandler(LOG_BUFFER))

    return logger


def get_logger(name: str = "copy-sync") -> logging.Logger:
    """Get standard Python logger"""
    return setup_logger(name)


def get_structured_logger(name: str = "copy-sync") -> structlog.BoundLogger:
    """Get structured logger with correlation ID support"""
    return structlog.get_logger(name)
