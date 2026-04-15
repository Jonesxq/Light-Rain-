"""Unit tests for backup database task helpers."""

from __future__ import annotations

import importlib
import io
from datetime import datetime, timedelta
from pathlib import Path

import pytest

backup_task_module = importlib.import_module("app.tasks.backup_database_task")


def _build_pg_config() -> dict:
    return {
        "db_type": "postgresql",
        "host": "localhost",
        "port": 5432,
        "user": "postgres",
        "password": "secret",
        "database": "official_proj",
    }


def test_parse_sqlite_aiosqlite_url_supports_driver_suffix():
    parsed = backup_task_module._parse_database_url("sqlite+aiosqlite:///./test.db")
    assert parsed["db_type"] == "sqlite"
    assert parsed["database_path"] == "./test.db"
    assert parsed["database"] == "test"


def test_parse_sqlite_memory_url_is_rejected():
    with pytest.raises(backup_task_module.NonRetryableBackupError):
        backup_task_module._parse_database_url("sqlite:///:memory:")


def test_normalize_database_name_keeps_real_database_identifier():
    assert backup_task_module._normalize_database_name("reporting/2026") == "reporting/2026"


def test_to_backup_file_name_sanitizes_path_like_input():
    backup_name = backup_task_module._to_backup_file_name("../evil")
    assert "/" not in backup_name
    assert "\\" not in backup_name
    assert backup_name.startswith("evil_")


def test_resolve_backup_dir_rejects_parent_escape():
    with pytest.raises(backup_task_module.NonRetryableBackupError):
        backup_task_module._resolve_backup_dir("../escape")


def test_resolve_backup_dir_allows_relative_subdirectory():
    resolved = backup_task_module._resolve_backup_dir("daily")
    expected = (backup_task_module.DEFAULT_BACKUP_ROOT.resolve() / "daily").resolve()
    assert resolved == expected


def test_cleanup_old_backups_only_deletes_expired(tmp_path: Path):
    db_name = "official_proj"
    old_file = tmp_path / f"{db_name}_backup_old.sql.gz"
    new_file = tmp_path / f"{db_name}_backup_new.sql.gz"

    old_file.write_text("old", encoding="utf-8")
    new_file.write_text("new", encoding="utf-8")

    old_mtime = (datetime.now() - timedelta(days=3)).timestamp()
    new_mtime = datetime.now().timestamp()
    old_file.touch()
    new_file.touch()
    # Preserve deterministic retention behavior.
    import os

    os.utime(old_file, (old_mtime, old_mtime))
    os.utime(new_file, (new_mtime, new_mtime))

    backup_task_module._cleanup_old_backups(tmp_path, db_name, retention_days=1)

    assert not old_file.exists()
    assert new_file.exists()


def test_dump_postgresql_does_not_use_verbose_flag(monkeypatch, tmp_path: Path):
    captured = {}

    class _FakeProcess:
        def __init__(self, stdout_handle):
            self.stderr = io.StringIO("")
            stdout_handle.write(b"-- mock dump --")

        def wait(self):
            return 0

    def _fake_popen(cmd, stdout, stderr, env, text, encoding, errors):
        captured["cmd"] = cmd
        assert env["PGPASSWORD"] == "secret"
        return _FakeProcess(stdout)

    monkeypatch.setattr(backup_task_module.subprocess, "Popen", _fake_popen)

    output_file = tmp_path / "backup.sql"
    backup_task_module._dump_postgresql(_build_pg_config(), output_file)

    assert "--verbose" not in captured["cmd"]
    assert output_file.exists()
    assert output_file.stat().st_size > 0


def test_dump_postgresql_retryable_error_detection(monkeypatch, tmp_path: Path):
    class _FakeProcess:
        def __init__(self):
            self.stderr = io.StringIO("could not connect to server: Connection refused\n")

        def wait(self):
            return 1

    def _fake_popen(cmd, stdout, stderr, env, text, encoding, errors):
        return _FakeProcess()

    monkeypatch.setattr(backup_task_module.subprocess, "Popen", _fake_popen)

    output_file = tmp_path / "backup.sql"
    with pytest.raises(backup_task_module.RetryableBackupError):
        backup_task_module._dump_postgresql(_build_pg_config(), output_file)


def test_dump_postgresql_non_retryable_error_detection(monkeypatch, tmp_path: Path):
    class _FakeProcess:
        def __init__(self):
            self.stderr = io.StringIO("pg_dump: error: syntax error at or near \"bad\"\n")

        def wait(self):
            return 1

    def _fake_popen(cmd, stdout, stderr, env, text, encoding, errors):
        return _FakeProcess()

    monkeypatch.setattr(backup_task_module.subprocess, "Popen", _fake_popen)

    output_file = tmp_path / "backup.sql"
    with pytest.raises(backup_task_module.NonRetryableBackupError):
        backup_task_module._dump_postgresql(_build_pg_config(), output_file)


def test_dump_mysql_unexpected_exception_defaults_to_non_retryable(monkeypatch, tmp_path: Path):
    def _fake_run(*_args, **_kwargs):
        raise ValueError("broken parser")

    monkeypatch.setattr(backup_task_module.subprocess, "run", _fake_run)

    output_file = tmp_path / "backup.sql"
    with pytest.raises(backup_task_module.NonRetryableBackupError):
        backup_task_module._dump_mysql(
            {
                "db_type": "mysql",
                "host": "localhost",
                "port": 3306,
                "user": "root",
                "password": "",
                "database": "db/main",
            },
            output_file,
        )


def test_is_retryable_exception_respects_custom_error_types():
    assert backup_task_module._is_retryable_exception(
        backup_task_module.RetryableBackupError("temporary")
    )
    assert not backup_task_module._is_retryable_exception(
        backup_task_module.NonRetryableBackupError("permanent")
    )
