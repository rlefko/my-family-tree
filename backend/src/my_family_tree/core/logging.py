"""Structured logging via structlog. JSON in prod, human-friendly in dev.

Bind context with `structlog.contextvars.bind_contextvars(request_id=..., ...)`
in middleware or worker job entry points; downstream logs inherit it.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, Processor


def _drop_color_message(_: Any, __: str, event_dict: EventDict) -> EventDict:
    """Uvicorn duplicates `event` into `color_message`. Drop the duplicate."""
    event_dict.pop("color_message", None)
    return event_dict


def configure_logging(*, level: str = "info", json_format: bool = True) -> None:
    """Configure stdlib `logging` and structlog to share a single output path.

    All third-party logs (uvicorn, sqlalchemy, asyncpg, boto) are routed through
    structlog so output is consistent and machine-parseable in prod.
    """
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        _drop_color_message,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_format:
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # Quiet noisy libraries unless we explicitly want their logs.
    for noisy in ("uvicorn.access", "botocore", "boto3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound logger. Use module `__name__` as `name`."""
    return structlog.get_logger(name)
