"""
studio/backend/logging_config.py
================================
Minimal structured logging for the Studio backend. Call configure_logging()
once at app startup. Modules then use the stdlib pattern:

    import logging
    logger = logging.getLogger(__name__)
    logger.info("...")

Replaces scattered print() diagnostics so logs carry a timestamp + level +
module and can be filtered/aggregated by Railway.
"""
from __future__ import annotations

import logging
import os
import sys

_configured = False

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s — %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

# Third-party loggers that emit one INFO line per HTTP call. Left at INFO they
# flood Railway with "HTTP Request: ... 200 OK" noise (e.g. the frontend's
# session poll to /auth/v1/user). Quieted to WARNING so only real problems show.
_NOISY_LOGGERS = ("httpx", "httpcore")

# Server loggers that install their own stderr handlers on startup. Without
# rerouting, their INFO output (uvicorn's "Application startup complete",
# access logs, etc.) lands on stderr and Railway flags every line as an error.
_SERVER_LOGGERS = (
    "uvicorn", "uvicorn.error", "uvicorn.access",
    "gunicorn", "gunicorn.error", "gunicorn.access",
)


def configure_logging() -> None:
    """Idempotent root logging setup. Honors LOG_LEVEL env (default INFO).

    Routes INFO/DEBUG to stdout and WARNING+ to stderr. Railway classifies a log
    line's severity by the stream it arrived on (stderr => "error"), so keeping
    routine logs on stdout stops normal INFO output from showing up as errors.
    """
    global _configured
    if _configured:
        return

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    stdout_h = logging.StreamHandler(sys.stdout)
    stdout_h.setLevel(logging.DEBUG)
    stdout_h.addFilter(lambda record: record.levelno < logging.WARNING)
    stdout_h.setFormatter(formatter)

    stderr_h = logging.StreamHandler(sys.stderr)
    stderr_h.setLevel(logging.WARNING)
    stderr_h.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(stdout_h)
    root.addHandler(stderr_h)

    for noisy in _NOISY_LOGGERS:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Drop uvicorn/gunicorn's own handlers and let their records propagate to
    # the root handlers above, so their logs get the same stdout/stderr split.
    for name in _SERVER_LOGGERS:
        server_logger = logging.getLogger(name)
        server_logger.handlers.clear()
        server_logger.propagate = True

    _configured = True
