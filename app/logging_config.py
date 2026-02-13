from logging.config import dictConfig
from pathlib import Path

from app.config import settings


def configure_logging() -> None:
    """Configure logging: console always; file only when LOG_DIR is set and writable."""
    handlers: dict = {
        "default": {
            "class": "rich.logging.RichHandler",
            "level": "DEBUG",
            "formatter": "console",
        },
    }
    logger_handlers = ["default"]

    logs_dir = (
        Path(settings.LOG_DIR)
        if settings.LOG_DIR
        else Path(__file__).parent.parent / "logs"
    )
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "formatter": "file",
            "filename": str(logs_dir / "app.log"),
            "maxBytes": 10485760,
            "backupCount": 5,
            "encoding": "utf-8",
        }
        logger_handlers.append("file")
    except OSError:
        pass

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "console": {
                    "class": "logging.Formatter",
                    "datefmt": "%Y-%m-%dT%H:%M:%S",
                    "format": "%(name)s:%(lineno)d - %(message)s",
                },
                "file": {
                    "class": "logging.Formatter",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                },
            },
            "handlers": handlers,
            "loggers": {
                "uvicorn": {"handlers": logger_handlers, "level": "INFO"},
                "app": {
                    "handlers": logger_handlers,
                    "level": "DEBUG" if settings.DEBUG else "INFO",
                    "propagate": False,
                },
            },
        }
    )
