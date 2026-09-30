import shutil
from pathlib import Path

from logger_manager import (
    DEFAULT_BACKUP_COUNT,
    DEFAULT_MAX_BYTES,
    LoggerManager,
    _parse_backup_count,
    _parse_console,
    _parse_log_level,
    _parse_max_bytes,
)


def test_parser_helpers():
    # max_bytes
    assert _parse_max_bytes("1024") == 1024
    assert _parse_max_bytes("invalid") == DEFAULT_MAX_BYTES
    assert _parse_max_bytes(None) == DEFAULT_MAX_BYTES
    assert _parse_max_bytes("-10") == DEFAULT_MAX_BYTES

    # backup_count
    assert _parse_backup_count("5") == 5
    assert _parse_backup_count("invalid") == DEFAULT_BACKUP_COUNT
    assert _parse_backup_count(None) == DEFAULT_BACKUP_COUNT

    # log_level
    import logging

    assert _parse_log_level("DEBUG") == logging.DEBUG
    assert _parse_log_level("info") == logging.INFO
    assert _parse_log_level("WARNING") == logging.WARNING
    assert _parse_log_level("error") == logging.ERROR
    assert _parse_log_level("CRITICAL") == logging.CRITICAL
    assert _parse_log_level("UNKNOWN") == logging.INFO

    # console
    assert _parse_console("true") is True
    assert _parse_console("True") is True
    assert _parse_console("1") is True
    assert _parse_console("yes") is True
    assert _parse_console("false") is False
    assert _parse_console("0") is False
    assert _parse_console("no") is False
    assert _parse_console("invalid", default=False) is False


def test_logger_manager_initialization_and_logging():
    folder = "test_system_init"
    lm = LoggerManager(folder_name=folder)
    assert lm.log_file.exists()
    assert lm.log_file.name == "activity.log"

    lm.info("User logged in successfully.")
    content = lm.log_file.read_text(encoding="utf-8")
    assert "INFO" in content
    assert "activity_logger" in content
    assert "User logged in successfully." in content
    assert "test_logger_manager_initialization_and_logging" in content

    # Clean up test folder
    shutil.rmtree(lm.log_dir, ignore_errors=True)


def test_logger_manager_utf8_multilingual_support():
    folder = "test_utf8"
    lm = LoggerManager(folder_name=folder)

    lm.info("English message")
    lm.info("ગુજરાતી text")
    lm.info("हिंदी text")
    lm.info("中文 text")

    content = lm.log_file.read_text(encoding="utf-8")
    assert "English message" in content
    assert "ગુજરાતી text" in content
    assert "हिंदी text" in content
    assert "中文 text" in content

    shutil.rmtree(lm.log_dir, ignore_errors=True)


def test_logger_manager_exception_traceback():
    folder = "test_exc"
    lm = LoggerManager(folder_name=folder)

    try:
        _ = 10 / 0
    except ZeroDivisionError:
        lm.exception("Division failure occurred.")

    content = lm.log_file.read_text(encoding="utf-8")
    assert "ERROR" in content
    assert "Division failure occurred." in content
    assert "ZeroDivisionError: division by zero" in content
    assert "Traceback (most recent call last)" in content

    shutil.rmtree(lm.log_dir, ignore_errors=True)


def test_duplicate_handlers_prevention():
    folder = "test_dup"
    # Clean previous run if any
    target_dir = Path("logs") / folder
    shutil.rmtree(target_dir, ignore_errors=True)

    lm1 = LoggerManager(folder_name=folder)
    lm2 = LoggerManager(folder_name=folder)

    assert lm1.logger is lm2.logger

    lm1.info("Single log line test")

    lines = [
        line
        for line in lm1.log_file.read_text(encoding="utf-8").splitlines()
        if "Single log line test" in line
    ]
    # Must appear exactly once, not duplicated
    assert len(lines) == 1

    shutil.rmtree(target_dir, ignore_errors=True)


def test_independent_multiple_folders():
    folder1 = "test_folder_alpha"
    folder2 = "test_folder_beta"

    lm1 = LoggerManager(folder_name=folder1)
    lm2 = LoggerManager(folder_name=folder2)

    lm1.info("Message for Alpha")
    lm2.info("Message for Beta")

    content1 = lm1.log_file.read_text(encoding="utf-8")
    content2 = lm2.log_file.read_text(encoding="utf-8")

    assert "Message for Alpha" in content1
    assert "Message for Beta" not in content1

    assert "Message for Beta" in content2
    assert "Message for Alpha" not in content2

    shutil.rmtree(lm1.log_dir, ignore_errors=True)
    shutil.rmtree(lm2.log_dir, ignore_errors=True)


def test_log_rotation_and_oldest_backup_deletion():
    folder = "test_rotation"
    target_dir = Path("logs") / folder
    shutil.rmtree(target_dir, ignore_errors=True)

    # Use small max_bytes and backup_count = 3
    lm = LoggerManager(
        folder_name=folder,
        logger_name="rot_logger",
        max_bytes=100,  # Small threshold to trigger rotation quickly
        backup_count=3,
    )

    # Write enough lines to trigger at least 4 rotations
    for i in range(1, 20):
        lm.info(f"Log rotation test message {i:02d} with padding " + "Z" * 80)

    log_files = sorted([f.name for f in target_dir.iterdir() if f.is_file()])

    # Maximum 1 active + 3 backups = 4 files maximum
    assert len(log_files) <= 4
    assert "activity.log" in log_files

    backup_files = [f for f in log_files if f != "activity.log"]
    assert len(backup_files) == 3

    # Confirm format of backups: activity_YYYY-MM-DD_NN.log
    for b in backup_files:
        assert b.startswith("activity_") and b.endswith(".log")

    # Clean up
    shutil.rmtree(target_dir, ignore_errors=True)
