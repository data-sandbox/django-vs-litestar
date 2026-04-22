import logging
import os


def setup_logging(level: str | None = None) -> None:
    """Configure structured JSON logging for the application."""
    from pythonjsonlogger.json import JsonFormatter

    log_level = level or os.getenv("LOG_LEVEL", "INFO")
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
        )
    )
    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()
    root.addHandler(handler)
