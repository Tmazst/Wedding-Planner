"""Small private audit trail for sensitive account and administrator actions."""

import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import current_app


def configure_security_logging(app):
    logger = logging.Logger(f"umshado.security.{id(app)}", level=logging.INFO)
    formatter = logging.Formatter("%(asctime)s UTC %(levelname)s %(message)s")
    path = Path(app.instance_path) / "security.log"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        os.close(descriptor)
        handler = RotatingFileHandler(path, maxBytes=1024 * 1024, backupCount=2)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    except OSError:
        app.logger.warning("event=security_log_file_unavailable")
    app.extensions["security_logger"] = logger


def security_event(event, **fields):
    values = ["event=" + re.sub(r"[^A-Za-z0-9_.-]", "_", event)[:64]]
    for key, value in fields.items():
        if value is not None:
            safe_key = re.sub(r"[^A-Za-z0-9_.-]", "_", str(key))[:40]
            safe_value = re.sub(r"[^A-Za-z0-9_.-]", "_", str(value))[:80]
            values.append(f"{safe_key}={safe_value}")
    logger = current_app.extensions.get("security_logger")
    if logger is not None:
        logger.info(" ".join(values))
