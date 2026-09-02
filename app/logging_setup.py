"""Application logging configuration.

Without this the app's ``logger.info/warning/exception`` calls go nowhere:
uvicorn configures only its own ``uvicorn.*`` loggers, the root logger has no
handler, and everything below WARNING is dropped while warnings reach stderr
only until the console window closes. A silently failing morning brief or
snapshot pipeline would be invisible for a week.

Logs go to ``data/logs/egx.log`` (rotating, 5 MB x 5) and to stderr.
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from app.config import PROJECT_ROOT, settings

_LOG_DIR = Path(settings.db_path).resolve().parent / "logs"
_LOG_FILE = _LOG_DIR / "egx.log"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUPS = 5
_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

_configured = False


def configure_logging(level: int = logging.INFO) -> Path | None:
    """Attach rotating-file + stderr handlers to the root logger.

    Idempotent: safe to call more than once (tests, reload). Returns the log
    file path, or None when the file handler could not be created.
    """
    global _configured
    if _configured:
        return _LOG_FILE if _LOG_FILE.exists() else None

    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter(_FORMAT)

    have_file = False
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            _LOG_FILE, maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root.addHandler(file_handler)
        have_file = True
    except OSError:
        # Read-only disk / permission problem — stderr logging still works.
        pass

    if not any(
        isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.handlers.RotatingFileHandler)
        for h in root.handlers
    ):
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        stream.setLevel(level)
        root.addHandler(stream)

    # Third-party noise floors.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler.executors").setLevel(logging.WARNING)

    _configured = True
    logging.getLogger("egx.logging").info(
        "logging configured (level=%s, file=%s)",
        logging.getLevelName(level),
        _LOG_FILE if have_file else "disabled",
    )
    return _LOG_FILE if have_file else None


__all__ = ["configure_logging", "PROJECT_ROOT"]
