
"""
Headless background worker for Hybrid Storage Management System.

Run with:
    python background_monitor.py

Starts Watchdog monitoring and the automatic tier optimizer without
opening the CustomTkinter GUI. Logs are written to logs/background_monitor.log.
"""

import logging
import os
import signal
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

from config import (
    LOCAL_SSD_PATH,
    LOCAL_SECONDARY_PATH,
    OPTIMIZATION_INTERVAL_SECONDS,
    BASE_DIR,
)
from database import initialize_database, discover_managed_files
from engine.migration_engine import reconcile_physical_state
from engine.tiering_engine import run_optimization_cycle
from storage.device_monitor import start_monitor, handle_storage_event


# --------------------------------------------------
# Logging configuration
# --------------------------------------------------

LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "background_monitor.log")

logger = logging.getLogger("hybrid_background")
logger.setLevel(logging.INFO)
logger.propagate = False

# Avoid duplicate handlers if this module is reloaded.
if not logger.handlers:
    handler = RotatingFileHandler(
        LOG_PATH,
        maxBytes=2_000_000,
        backupCount=4,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    )
    logger.addHandler(handler)


class StreamToLogger:
    """Redirect print output from existing monitor code into the log."""

    def __init__(self, level):
        self.level = level
        self.buffer = ""

    def write(self, message):
        if not message:
            return

        self.buffer += message

        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if line.strip():
                logger.log(self.level, line.rstrip())

    def flush(self):
        if self.buffer.strip():
            logger.log(self.level, self.buffer.rstrip())
        self.buffer = ""


stop_event = threading.Event()
monitors = []


def request_stop(signum=None, frame=None):
    """Request a graceful shutdown."""
    logger.info("Stop requested; shutting down monitors.")
    stop_event.set()


def start_one_monitor(path, label):
    """Start monitoring one storage folder if it is available."""

    if not os.path.isdir(path):
        logger.warning(
            "%s folder is unavailable; skipped: %s",
            label,
            path,
        )
        return None

    try:
        monitor = start_monitor(path, handle_storage_event)

        # Allow the observer thread to initialize.
        time.sleep(0.5)

        if monitor.is_healthy():
            logger.info("%s monitoring started: %s", label, path)
        else:
            logger.warning(
                "%s monitor did not report healthy yet: %s",
                label,
                path,
            )

        return monitor

    except Exception:
        logger.exception(
            "Could not start %s monitor for %s",
            label,
            path,
        )
        return None


def main():
    """Initialize storage, start monitors, and run the optimizer."""

    # Preserve filesystem event output when launched through pythonw.exe.
    sys.stdout = StreamToLogger(logging.INFO)
    sys.stderr = StreamToLogger(logging.ERROR)

    signal.signal(signal.SIGINT, request_stop)

    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    logger.info("=" * 60)
    logger.info("Hybrid Storage background monitor starting")
    logger.info("Python executable: %s", sys.executable)
    logger.info("Project directory: %s", BASE_DIR)
    logger.info("SSD path: %s", LOCAL_SSD_PATH)
    logger.info("Secondary path: %s", LOCAL_SECONDARY_PATH)

    # Initialize database and reconcile the physical storage state.
    try:
        initialize_database()

        repaired = reconcile_physical_state()
        if repaired:
            logger.info("Reconciled %s block(s)", len(repaired))

        discovered = discover_managed_files([
            ("SSD", LOCAL_SSD_PATH),
            ("SECONDARY", LOCAL_SECONDARY_PATH),
        ])

        logger.info(
            "Startup discovery synchronized %s file(s)",
            len(discovered or []),
        )

    except Exception:
        logger.exception("Database initialization/reconciliation failed")
        raise

    # Start both storage monitors.
    for path, label in (
        (LOCAL_SSD_PATH, "SSD"),
        (LOCAL_SECONDARY_PATH, "SECONDARY"),
    ):
        monitor = start_one_monitor(path, label)
        if monitor:
            monitors.append(monitor)

    if not monitors:
        logger.error(
            "No storage monitors started. Check configured folders/drives."
        )

    logger.info(
        "Background monitoring is running. "
        "Close via Task Manager or Ctrl+C."
    )

    # First routine optimization summary will be logged after five minutes.
    last_summary_time = time.monotonic()

    try:
        while not stop_event.wait(
            max(1, OPTIMIZATION_INTERVAL_SECONDS)
        ):

            # Reconnect monitors if a storage drive becomes available again.
            for path, label in (
                (LOCAL_SSD_PATH, "SSD"),
                (LOCAL_SECONDARY_PATH, "SECONDARY"),
            ):
                healthy = any(
                    monitor.drive_path == path and monitor.is_healthy()
                    for monitor in monitors
                )

                if not healthy:
                    # Remove stale entries before attempting a restart.
                    monitors[:] = [
                        monitor
                        for monitor in monitors
                        if monitor.drive_path != path
                    ]

                    new_monitor = start_one_monitor(path, label)
                    if new_monitor:
                        monitors.append(new_monitor)

            # Run one automatic optimization cycle.
            try:
                result = run_optimization_cycle()
                migrations = result.get("migrations", [])
                now = time.monotonic()

                # Log routine summaries at most every five minutes.
                # Always log a cycle that reports migrations.
                if migrations or now - last_summary_time >= 300:
                    logger.info(
                        "Optimization cycle complete: refreshed=%s migrations=%s",
                        result.get("temperatures_refreshed", 0),
                        len(migrations),
                    )
                    last_summary_time = now

                # Preserve every migration record.
                for item in migrations:
                    logger.info(
                        "Migration: block=%s action=%s detail=%s",
                        item.get("block_id"),
                        item.get("action"),
                        item.get("message"),
                    )

            except Exception:
                logger.exception("Optimization cycle failed")

    finally:
        # Stop all active filesystem observers cleanly.
        for monitor in monitors:
            try:
                monitor.stop()
            except Exception:
                logger.exception(
                    "Error while stopping monitor %s",
                    monitor.drive_path,
                )

        logger.info("Background monitor stopped.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception(
            "Background monitor exited due to an unrecoverable error"
        )
        raise
