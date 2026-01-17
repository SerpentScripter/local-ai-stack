"""
Structured Logging Configuration
JSON-formatted logging for the Local AI Hub API
"""
import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

# Log directory
LOG_DIR = Path(__file__).parent.parent / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Log level from environment
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, "extra_data"):
            log_entry["data"] = record.extra_data

        return json.dumps(log_entry)


class StructuredLogger(logging.Logger):
    """Extended logger with structured data support"""

    def _log_with_data(self, level: int, msg: str, data: dict = None, *args, **kwargs):
        """Log with optional structured data"""
        extra = kwargs.pop("extra", {})
        if data:
            extra["extra_data"] = data
        kwargs["extra"] = extra
        super().log(level, msg, *args, **kwargs)

    def info_data(self, msg: str, data: dict = None, *args, **kwargs):
        """Log info with structured data"""
        self._log_with_data(logging.INFO, msg, data, *args, **kwargs)

    def error_data(self, msg: str, data: dict = None, *args, **kwargs):
        """Log error with structured data"""
        self._log_with_data(logging.ERROR, msg, data, *args, **kwargs)

    def warning_data(self, msg: str, data: dict = None, *args, **kwargs):
        """Log warning with structured data"""
        self._log_with_data(logging.WARNING, msg, data, *args, **kwargs)

    def debug_data(self, msg: str, data: dict = None, *args, **kwargs):
        """Log debug with structured data"""
        self._log_with_data(logging.DEBUG, msg, data, *args, **kwargs)


def setup_logging(name: str = "api") -> StructuredLogger:
    """
    Set up structured JSON logging

    Args:
        name: Logger name

    Returns:
        Configured StructuredLogger instance
    """
    # Register custom logger class
    logging.setLoggerClass(StructuredLogger)

    # Get or create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOG_LEVEL))

    # Remove existing handlers
    logger.handlers = []

    # Console handler (JSON format)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(JSONFormatter())
    logger.addHandler(console_handler)

    # File handler (JSON format, rotating)
    log_file = LOG_DIR / f"{name}.jsonl"
    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)

    return logger


# Pre-configured loggers for different modules
api_logger = setup_logging("api")
agent_logger = setup_logging("agent")
service_logger = setup_logging("service")


def log_request(method: str, path: str, status_code: int, duration_ms: float, user: str = None):
    """Log an API request"""
    api_logger.info_data(
        f"{method} {path} - {status_code}",
        data={
            "type": "request",
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
            "user": user
        }
    )


def log_agent_event(agent_type: str, event: str, session_id: str = None, data: dict = None):
    """Log an agent event"""
    agent_logger.info_data(
        f"Agent {agent_type}: {event}",
        data={
            "type": "agent_event",
            "agent_type": agent_type,
            "event": event,
            "session_id": session_id,
            **(data or {})
        }
    )


def log_service_event(service_id: str, action: str, status: str, error: str = None):
    """Log a service control event"""
    service_logger.info_data(
        f"Service {service_id}: {action} -> {status}",
        data={
            "type": "service_event",
            "service_id": service_id,
            "action": action,
            "status": status,
            "error": error
        }
    )
