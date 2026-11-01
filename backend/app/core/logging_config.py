import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_context: ContextVar[str] = ContextVar("faultline_request_id", default="-")


class JsonLogFormatter(logging.Formatter):
    """Emit bounded structured fields without exception messages or request bodies."""

    _EXTRA_FIELDS = (
        "method",
        "path",
        "status_code",
        "duration_ms",
        "error_type",
        "error_code",
    )

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_context.get(),
        }
        for field in self._EXTRA_FIELDS:
            value = getattr(record, field, None)
            if isinstance(value, (str, int, float)):
                entry[field] = value
        return json.dumps(entry, separators=(",", ":"), ensure_ascii=True)


def configure_logging(level: str) -> None:
    for logger_name in ("app", "faultline"):
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        logger.propagate = False
        if logger.handlers:
            for handler in logger.handlers:
                handler.setFormatter(JsonLogFormatter())
        else:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(JsonLogFormatter())
            logger.addHandler(handler)


def safe_error_log(logger: logging.Logger, message: str, error: Exception) -> None:
    """Log the exception class only; messages and tracebacks can contain secrets or source."""
    logger.error(message, extra={"error_type": type(error).__name__})
