"""Logging helpers for terminal + optional log file."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


LOGGER_NAME = "standing"


def setup_logging(
    *,
    verbose: bool = False,
    log_file: Path | None = None,
    stream=None,
) -> logging.Logger:
    """Configure logging. Default stream is stdout; worker mode should pass stderr."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-5s  %(message)s",
        datefmt="%H:%M:%S",
    )

    console = logging.StreamHandler(stream or sys.stdout)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(fmt)
    logger.addHandler(console)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
        logger.info("Logging to %s", log_file)

    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)
