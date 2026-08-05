"""Consistent rotating, structured service logs."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from app.config import FieldMouseConfig


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(service: str, config: FieldMouseConfig) -> logging.Logger:
    config.storage.logs_directory.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(service)
    logger.setLevel(config.logging.level.upper())
    logger.handlers.clear()
    handler = RotatingFileHandler(
        config.storage.logs_directory / f"{service}.log",
        maxBytes=config.logging.max_bytes,
        backupCount=config.logging.backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(
        JsonFormatter() if config.logging.json else
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(handler)
    logger.propagate = False
    return logger
