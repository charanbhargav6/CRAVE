"""
CRAVE — Logging Configuration
Save to: D:\\CRAVE\\src\\core\\logging_config.py

Sets up structured logging for all CRAVE modules:
  - crave.log: main system events (rotating, 5MB, 3 backups)
  - security_events.log: auth attempts, lockdowns, vault access
  - Console: colored output for terminal debugging

Call setup_logging() ONCE at startup from main.py.
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler

CRAVE_ROOT = os.environ.get("CRAVE_ROOT", r"D:\CRAVE")
LOGS_DIR = os.path.join(CRAVE_ROOT, "Logs")


def setup_logging(level: int = logging.INFO) -> None:
    """
    Configure all CRAVE loggers with file + console handlers.
    Call this once at the start of main.py.
    """
    # Ensure logs directory exists
    os.makedirs(LOGS_DIR, exist_ok=True)

    # ── Root logger ──
    root = logging.getLogger()
    root.setLevel(level)

    # Don't add handlers twice (e.g. if called multiple times)
    if root.handlers:
        return

    # ── Format ──
    file_fmt = logging.Formatter(
        "%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S"
    )

    # ── Main log file (crave.log) ──
    main_handler = RotatingFileHandler(
        os.path.join(LOGS_DIR, "crave.log"),
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8"
    )
    main_handler.setLevel(logging.INFO)
    main_handler.setFormatter(file_fmt)
    root.addHandler(main_handler)

    # ── Security log file (security_events.log) ──
    sec_handler = RotatingFileHandler(
        os.path.join(LOGS_DIR, "security_events.log"),
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8"
    )
    sec_handler.setLevel(logging.INFO)
    sec_handler.setFormatter(file_fmt)
    # Only capture security-specific loggers
    sec_filter = logging.Filter("crave.security")
    sec_handler.addFilter(sec_filter)
    root.addHandler(sec_handler)

    # ── Console output ──
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_fmt)
    root.addHandler(console_handler)

    # ── Suppress noisy third-party loggers ──
    for noisy in ["urllib3", "httpx", "httpcore", "asyncio", "telegram"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("crave").info("Logging initialized — writing to %s", LOGS_DIR)
