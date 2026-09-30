"""Production-ready centralized application and activity logger utility.

Provides automated size-based log rotation (1 GiB max active log, maximum 3 backups,
purging oldest backup on rollover), .env-based configuration with fallback defaults,
thread-safe operation, duplicate-handler prevention, and clean caller-stack tracing.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar

from dotenv import load_dotenv

# Resolve project root based on logger_manager.py location
PROJECT_ROOT: Path = Path(__file__).resolve().parent

# Load environment configuration from .env file if present
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

# Hardcoded fallback defaults
DEFAULT_MAX_BYTES: int = 1 * 1024 * 1024 * 1024  # 1 GiB = 1,073,741,824 bytes
DEFAULT_BACKUP_COUNT: int = 3
DEFAULT_LOG_LEVEL: str = "INFO"
DEFAULT_CONSOLE: bool = False
DEFAULT_LOGGER_NAME: str = "activity_logger"
DEFAULT_LOG_FILENAME: str = "activity.log"
LOG_FORMAT: str = (
    "%(asctime)s | %(levelname)s | %(name)s | %(filename)s | "
    "%(funcName)s | %(lineno)d | %(message)s"
)
LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"


def _parse_max_bytes(val: Any, default: int = DEFAULT_MAX_BYTES) -> int:
    """Safely parse maximum log file size in bytes."""
    if val is None:
        return default
    try:
        parsed = int(str(val).strip())
        return parsed if parsed > 0 else default
    except (ValueError, TypeError):
        return default


def _parse_backup_count(val: Any, default: int = DEFAULT_BACKUP_COUNT) -> int:
    """Safely parse maximum backup count."""
    if val is None:
        return default
    try:
        parsed = int(str(val).strip())
        return parsed if parsed >= 0 else default
    except (ValueError, TypeError):
        return default


def _parse_log_level(val: Any, default: str = DEFAULT_LOG_LEVEL) -> int:
    """Safely parse logging level string or int to logging level constant."""
    if val is None:
        val = default
    if isinstance(val, int):
        return val

    level_str = str(val).strip().upper()
    levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "WARN": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
        "FATAL": logging.CRITICAL,
    }
    return levels.get(level_str, logging.INFO)


def _parse_console(val: Any, default: bool = DEFAULT_CONSOLE) -> bool:
    """Safely parse boolean value for console logging."""
    if val is None:
        return default
    if isinstance(val, bool):
        return val

    normalized = str(val).strip().lower()
    if normalized in ("true", "1", "yes", "y", "t", "on"):
        return True
    if normalized in ("false", "0", "no", "n", "f", "off"):
        return False
    return default


class _LoggerNameFilter(logging.Filter):
    """Ensures record.name reflects the public logger_name rather than internal hierarchy."""

    def __init__(self, display_name: str) -> None:
        super().__init__()
        self.display_name = display_name

    def filter(self, record: logging.LogRecord) -> bool:
        record.name = self.display_name
        return True


class DailySequentialRotatingFileHandler(RotatingFileHandler):
    """Custom rotating file handler with dated sequence backup naming.

    Rolls over 'activity.log' into 'activity_YYYY-MM-DD_NN.log', ensuring at most
    `backupCount` backups exist by permanently deleting the oldest backup before
    retaining the new backup.
    """

    BACKUP_PATTERN = re.compile(r"^activity_(\d{4}-\d{2}-\d{2})_(\d+)\.log$")

    def _get_existing_backups(self) -> list[tuple[datetime, int, float, Path]]:
        """Retrieve all existing backup files sorted chronologically from oldest to newest."""
        directory = Path(self.baseFilename).parent
        backups: list[tuple[datetime, int, float, Path]] = []

        if not directory.exists():
            return []

        active_filename = Path(self.baseFilename).name
        for file_path in directory.iterdir():
            if not file_path.is_file() or file_path.name == active_filename:
                continue

            match = self.BACKUP_PATTERN.match(file_path.name)
            if match:
                date_str, seq_str = match.groups()
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(
                        tzinfo=timezone.utc
                    )
                    seq = int(seq_str)
                    mtime = file_path.stat().st_mtime
                    backups.append((dt, seq, mtime, file_path))
                except (ValueError, OSError):
                    continue
            elif file_path.name.startswith("activity_") and file_path.name.endswith(
                ".log"
            ):
                try:
                    mtime = file_path.stat().st_mtime
                    backups.append(
                        (datetime.min.replace(tzinfo=timezone.utc), 0, mtime, file_path)
                    )
                except OSError:
                    continue

        # Sort by date, sequence number, then file modification time
        backups.sort(key=lambda item: (item[0], item[1], item[2]))
        return backups

    def _get_next_backup_path(self) -> Path:
        """Determine next backup path for current date with incrementing sequence number."""
        directory = Path(self.baseFilename).parent
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_regex = re.compile(rf"^activity_{re.escape(today_str)}_(\d+)\.log$")

        max_seq = 0
        if directory.exists():
            for file_path in directory.iterdir():
                if file_path.is_file():
                    match = today_regex.match(file_path.name)
                    if match:
                        try:
                            seq = int(match.group(1))
                            max_seq = max(max_seq, seq)
                        except ValueError:
                            pass

        next_seq = max_seq + 1
        return directory / f"activity_{today_str}_{next_seq:02d}.log"

    def doRollover(self) -> None:
        """Perform log rotation when maxBytes threshold is reached.

        1. Close active stream.
        2. Delete oldest backup(s) so total backups after rotation <= backupCount.
        3. Rename 'activity.log' to 'activity_YYYY-MM-DD_NN.log'.
        4. Reopen fresh 'activity.log'.
        """
        if self.stream:
            self.stream.close()
            self.stream = None

        active_path = Path(self.baseFilename)
        if active_path.exists():
            if self.backupCount > 0:
                backups = self._get_existing_backups()
                # Ensure we delete the oldest backup before adding the new one
                while len(backups) >= self.backupCount:
                    oldest_entry = backups.pop(0)
                    oldest_file = oldest_entry[3]
                    try:
                        oldest_file.unlink(missing_ok=True)
                    except OSError:
                        pass

                new_backup_path = self._get_next_backup_path()
                try:
                    active_path.rename(new_backup_path)
                except OSError:
                    # Fallback on OS locking edge cases
                    try:
                        import shutil

                        shutil.copy2(active_path, new_backup_path)
                        active_path.write_text("", encoding="utf-8")
                    except OSError:
                        pass
            else:
                try:
                    active_path.unlink(missing_ok=True)
                except OSError:
                    active_path.write_text("", encoding="utf-8")

        if not self.delay:
            self.stream = self._open()


class LoggerManager:
    """Reusable centralized logger manager with automated log rotation.

    Features:
    - Stores logs in <project_root>/logs/<folder_name>/activity.log
    - Automatic size-based rotation (default 1 GiB)
    - Retains maximum 3 backup files (activity_YYYY-MM-DD_NN.log)
    - Automatically deletes oldest backup upon rollover
    - .env-driven configuration with priority: Constructor > .env > Hardcoded
    - Prevents duplicate handlers across multiple instances
    - Thread-safe and compatible with Python 3.11+
    """

    _lock: ClassVar[threading.Lock] = threading.Lock()
    _configured_loggers: ClassVar[dict[str, logging.Logger]] = {}

    def __init__(
        self,
        folder_name: str = "system",
        logger_name: str | None = None,
        max_bytes: int | None = None,
        backup_count: int | None = None,
        level: str | int | None = None,
        console: bool | None = None,
    ) -> None:
        """Initialize or reuse a LoggerManager instance.

        Args:
            folder_name: Subdirectory inside <project_root>/logs (e.g. 'system', 'api').
            logger_name: Name of the logger displayed in log records.
            max_bytes: Maximum log file size in bytes before rollover (default: 1 GiB).
            backup_count: Maximum backup files to retain (default: 3).
            level: Logging level (e.g. 'DEBUG', 'INFO', 'WARNING', 'ERROR').
            console: If True, also output logs to the console/terminal.
        """
        self.folder_name: str = (folder_name or "system").strip().strip("/")
        self.logger_name: str = (logger_name or DEFAULT_LOGGER_NAME).strip()

        # Resolve configuration with priority: Constructor -> .env -> Hardcoded default
        self.max_bytes: int = (
            max_bytes
            if max_bytes is not None
            else _parse_max_bytes(os.getenv("LOG_MAX_BYTES"), DEFAULT_MAX_BYTES)
        )
        self.backup_count: int = (
            backup_count
            if backup_count is not None
            else _parse_backup_count(
                os.getenv("LOG_BACKUP_COUNT"), DEFAULT_BACKUP_COUNT
            )
        )
        raw_level = (
            level if level is not None else os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL)
        )
        self.level: int = _parse_log_level(raw_level, DEFAULT_LOG_LEVEL)
        self.console: bool = (
            console
            if console is not None
            else _parse_console(os.getenv("LOG_CONSOLE"), DEFAULT_CONSOLE)
        )

        # Setup directory and files
        self.log_dir: Path = PROJECT_ROOT / "logs" / self.folder_name
        self.log_file: Path = self.log_dir / DEFAULT_LOG_FILENAME

        # Initialize internal logger safely
        self._logger: logging.Logger = self._get_or_create_logger()

    def _get_or_create_logger(self) -> logging.Logger:
        """Create or reuse a configured Logger instance, preventing duplicate handlers."""
        # Unique key based on target log file path and logger name
        registry_key = f"{self.log_file.resolve()}:{self.logger_name}"

        with self._lock:
            if registry_key in self._configured_loggers:
                existing_logger = self._configured_loggers[registry_key]
                # Update level in case instance requested different level
                existing_logger.setLevel(self.level)
                return existing_logger

            self.log_dir.mkdir(parents=True, exist_ok=True)

            # Namespaced logger name to isolate from root and prevent collisions
            internal_name = f"logger_manager.{self.folder_name}.{self.logger_name}"
            logger = logging.getLogger(internal_name)
            logger.setLevel(self.level)
            logger.propagate = False
            logger.handlers.clear()

            # Formatter & Filter
            formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
            name_filter = _LoggerNameFilter(self.logger_name)

            # Rotating file handler
            file_handler = DailySequentialRotatingFileHandler(
                filename=str(self.log_file),
                maxBytes=self.max_bytes,
                backupCount=self.backup_count,
                encoding="utf-8",
            )
            file_handler.setLevel(self.level)
            file_handler.setFormatter(formatter)
            file_handler.addFilter(name_filter)
            logger.addHandler(file_handler)

            # Optional console stream handler
            if self.console:
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setLevel(self.level)
                console_handler.setFormatter(formatter)
                console_handler.addFilter(name_filter)
                logger.addHandler(console_handler)

            self._configured_loggers[registry_key] = logger
            return logger

    @property
    def logger(self) -> logging.Logger:
        """Return the underlying Python logging.Logger instance."""
        return self._logger

    def debug(self, msg: object, *args: object, **kwargs: Any) -> None:
        """Log a message with severity 'DEBUG'."""
        kwargs.setdefault("stacklevel", 2)
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg: object, *args: object, **kwargs: Any) -> None:
        """Log a message with severity 'INFO'."""
        kwargs.setdefault("stacklevel", 2)
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg: object, *args: object, **kwargs: Any) -> None:
        """Log a message with severity 'WARNING'."""
        kwargs.setdefault("stacklevel", 2)
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg: object, *args: object, **kwargs: Any) -> None:
        """Log a message with severity 'ERROR'."""
        kwargs.setdefault("stacklevel", 2)
        self._logger.error(msg, *args, **kwargs)

    def critical(self, msg: object, *args: object, **kwargs: Any) -> None:
        """Log a message with severity 'CRITICAL'."""
        kwargs.setdefault("stacklevel", 2)
        self._logger.critical(msg, *args, **kwargs)

    def exception(
        self, msg: object, *args: object, exc_info: Any = True, **kwargs: Any
    ) -> None:
        """Log a message with severity 'ERROR' including exception traceback."""
        kwargs.setdefault("stacklevel", 2)
        self._logger.exception(msg, *args, exc_info=exc_info, **kwargs)

    def log(self, level: int, msg: object, *args: object, **kwargs: Any) -> None:
        """Log a message with integer level severity."""
        kwargs.setdefault("stacklevel", 2)
        self._logger.log(level, msg, *args, **kwargs)

    def __repr__(self) -> str:
        return (
            f"<LoggerManager name={self.logger_name!r} folder={self.folder_name!r} "
            f"level={logging.getLevelName(self.level)} file={self.log_file.name!r}>"
        )
