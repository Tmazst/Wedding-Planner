"""Private, bounded payment event trail. Never log gateway request/response bodies."""

import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import current_app


def configure_payment_logging(app):
    logger = logging.Logger("umshado.payments", level=logging.INFO)
    formatter = logging.Formatter("%(asctime)s UTC %(levelname)s %(message)s")
    stderr = logging.StreamHandler(sys.stderr)
    stderr.setFormatter(formatter)
    logger.addHandler(stderr)

    path = Path(app.instance_path) / "payments.log"
    try:
        # Existing instance/ is created by the app and must be writable by Gunicorn.
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        os.close(descriptor)
        file_handler = RotatingFileHandler(path, maxBytes=2 * 1024 * 1024, backupCount=2)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        logger.warning("event=payment_log_file_unavailable")

    app.extensions["payment_logger"] = logger


def payment_event(event, **fields):
    # Restrict values to one safe line even if the gateway returns malformed IDs.
    values = ["event=" + re.sub(r"[^A-Za-z0-9_.-]", "_", event)[:64]]
    for key, value in fields.items():
        if value is not None:
            values.append(f'{key}={re.sub(r"[^A-Za-z0-9_.-]", "_", str(value))[:80]}')
    current_app.extensions["payment_logger"].info(" ".join(values))
