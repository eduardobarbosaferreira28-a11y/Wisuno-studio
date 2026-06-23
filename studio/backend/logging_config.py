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

_configured = False

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s — %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def configure_logging() -> None:
    """Idempotent root logging setup. Honors LOG_LEVEL env (default INFO)."""
    global _configured
    if _configured:
        return

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logging.basicConfig(level=level, format=_FORMAT, datefmt=_DATEFMT)
    _configured = True
