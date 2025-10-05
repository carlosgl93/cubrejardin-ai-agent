"""Structured logging configuration."""

import json
import logging
import sys
from typing import Any, Dict


class JsonFormatter(logging.Formatter):
    """Format log records as JSON."""

    def format(self, record: logging.LogRecord) -> str:
        base: Dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }
        if record.exc_info:
            base["exception"] = self.formatException(record.exc_info)
        if record.__dict__.get("extra"):
            base.update(record.__dict__["extra"])
        return json.dumps(base, ensure_ascii=False)


def configure_logger() -> logging.Logger:
    """Configure application logger."""

    logger = logging.getLogger("whatsapp_ai_agent")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.handlers = [handler]
    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    """Return configured logger singleton."""

    return configure_logger()


logger = get_logger()
