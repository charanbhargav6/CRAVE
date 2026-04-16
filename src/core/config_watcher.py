"""
CRAVE — Hot-Reload Config Watcher
Save to: D:\\CRAVE\\src\\core\\config_watcher.py

Monitors hardware.json for modifications. When changed,
it safely triggers an update event so modules can refresh
their configuration in-memory without restarting the system.
"""

import os
import sys
import time
import json
import logging
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger("crave.core.config_watcher")

# Global event that other modules can wait on
CONFIG_RELOAD_EVENT = threading.Event()


class ConfigReloadHandler(FileSystemEventHandler):
    def __init__(self, target_file: str):
        super().__init__()
        self.target_file = os.path.abspath(target_file)

    def on_modified(self, event):
        # Watchdog can trigger multiple times for a single save
        if not event.is_directory and os.path.abspath(event.src_path) == self.target_file:
            logger.info("[ConfigWatcher] hardware.json change detected. Signaling reload.")
            CONFIG_RELOAD_EVENT.set()
            # Auto-clear the event after a short delay so it can trigger again
            threading.Timer(2.0, CONFIG_RELOAD_EVENT.clear).start()


class ConfigWatcher:
    """Singleton to manage the watchdog thread."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._observer = None
        return cls._instance

    def start_watching(self, config_path: str):
        if self._observer is not None:
            return  # Already watching

        logger.info(f"[ConfigWatcher] Starting hot-reload watch on: {config_path}")
        abs_path = os.path.abspath(config_path)
        directory = os.path.dirname(abs_path)

        event_handler = ConfigReloadHandler(abs_path)
        self._observer = Observer()
        self._observer.schedule(event_handler, path=directory, recursive=False)
        self._observer.start()

    def stop_watching(self):
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None
            logger.info("[ConfigWatcher] Stopped hardware.json watcher.")
