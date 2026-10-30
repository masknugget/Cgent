"""Small JSON logging setup with request-scoped correlation fields."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from cgent.telemetry.request_id import (
    current_execution_id,
    current_invocation_id,
    current_request_id,
)

_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in (
            ("request_id", current_request_id()),
            ("invocation_id", current_invocation_id()),
            ("execution_id", current_execution_id()),
        ):
            if value:
                payload[key] = value
        fields = getattr(record, "cgent_fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key != "cgent_fields" and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def log_event(logger: logging.Logger, level: int, message: str, **fields: object) -> None:
    logger.log(level, message, extra={"cgent_fields": fields})
