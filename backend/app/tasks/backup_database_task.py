"""数据库备份任务：导出 MySQL/PostgreSQL/SQLite 并压缩归档。"""
import errno
import glob
import gzip
import hashlib
import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse
from typing import Optional

from app.core.celery import celery_app, with_db_init
from app.core.config.settings import settings
from app.core.logger import logger_manager

logger = logger_manager.get_logger(__name__)

DEFAULT_BACKUP_ROOT = Path("./backups/database")
BACKUP_FILE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")
BACKUP_FILE_NAME_MAX_LEN = 128
RETRYABLE_ERROR_KEYWORDS = (
    "timed out",
    "timeout",
    "connection refused",
    "could not connect",
    "too many connections",
    "temporarily unavailable",
    "connection reset",
    "broken pipe",
    "network is unreachable",
    "try again",
    "server closed the connection unexpectedly",
    "resource temporarily unavailable",
    "deadlock",
    "lock wait timeout",
)
RETRYABLE_OS_ERROR_NAMES = (
    "EAGAIN",
    "ECONNRESET",
    "ECONNREFUSED",
    "ETIMEDOUT",
    "ENETDOWN",
    "ENETUNREACH",
    "EHOSTUNREACH",
)
RETRYABLE_OS_ERRNOS = {
    getattr(errno, name) for name in RETRYABLE_OS_ERROR_NAMES if hasattr(errno, name)
}
PG_DUMP_STDERR_TAIL_LINES = 80
ERROR_MESSAGE_MAX_CHARS = 4000


class BackupTaskError(Exception):
    """备份任务异常基类。"""


class RetryableBackupError(BackupTaskError):
    """可重试异常。"""


class NonRetryableBackupError(BackupTaskError):
    """不可重试异常。"""


def _trim_error_message(message: str) -> str:
    """截断超长错误，避免日志和任务结果过大。"""
    normalized = message.strip()
    if len(normalized) <= ERROR_MESSAGE_MAX_CHARS:
        return normalized
    return f"...{normalized[-ERROR_MESSAGE_MAX_CHARS:]}"


def _is_retryable_error_message(message: str) -> bool:
    """通过关键字判定错误是否更像临时性失败。"""
    lower_message = message.lower()
    return any(keyword in lower_message for keyword in RETRYABLE_ERROR_KEYWORDS)


def _raise_dump_error(tool_name: str, error_msg: str) -> None:
    """根据错误内容抛出可重试/不可重试异常。"""
    normalized = _trim_error_message(error_msg)
    if _is_retryable_error_message(normalized):
        raise RetryableBackupError(f"{tool_name} execution failed: {normalized}")
    raise NonRetryableBackupError(f"{tool_name} execution failed: {normalized}")


def _is_retryable_exception(exc: Exception) -> bool:
    """分类是否需要进入 Celery retry。"""
    if isinstance(exc, RetryableBackupError):
        return True
    if isinstance(exc, NonRetryableBackupError):
        return False
    if isinstance(exc, subprocess.TimeoutExpired):
        return True
    if isinstance(exc, OSError):
        return exc.errno in RETRYABLE_OS_ERRNOS
    return False


def _raise_unexpected_dump_error(tool_name: str, exc: Exception) -> None:
    """兜底异常分类：默认不可重试，仅对临时性错误标记为可重试。"""
    message = f"Error exporting {tool_name} database: {exc}"
    if _is_retryable_exception(exc) or _is_retryable_error_message(str(exc)):
        raise RetryableBackupError(message) from exc
    raise NonRetryableBackupError(message) from exc


def _is_path_within(path: Path, base_dir: Path) -> bool:
    """判断 path 是否位于 base_dir 内。"""
    try:
        path.relative_to(base_dir)
        return True
    except ValueError:
        return False


def _resolve_backup_dir(backup_dir: Optional[str]) -> Path:
    """解析备份目录并强制限制在默认根目录内。"""
    allowed_root = DEFAULT_BACKUP_ROOT.resolve()

    if not backup_dir:
        return allowed_root

    user_path = Path(backup_dir)
    resolved_path = user_path.resolve() if user_path.is_absolute() else (allowed_root / user_path).resolve()

    if not _is_path_within(resolved_path, allowed_root):
        raise NonRetryableBackupError(
            f"backup_dir must be within '{allowed_root}', got '{resolved_path}'"
        )
    return resolved_path


def _normalize_database_name(database_name: str) -> str:
    """标准化数据库名（用于导出目标），仅做非空校验。"""
    name = database_name.strip()
    if not name:
        raise NonRetryableBackupError("Database name cannot be empty")
    return name


def _to_backup_file_name(database_name: str) -> str:
    """将数据库名转换为安全文件名前缀，不影响真实导出库名。"""
    normalized = _normalize_database_name(database_name)
    sanitized = BACKUP_FILE_NAME_PATTERN.sub("_", normalized).strip("._-")

    if not sanitized:
        sanitized = "database"

    if sanitized != normalized:
        digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:8]
        max_base_len = BACKUP_FILE_NAME_MAX_LEN - len(digest) - 1
        sanitized = f"{sanitized[:max_base_len]}_{digest}"
    elif len(sanitized) > BACKUP_FILE_NAME_MAX_LEN:
        sanitized = sanitized[:BACKUP_FILE_NAME_MAX_LEN]

    return sanitized


def _extract_sqlite_database_path(parsed) -> str:
    """从 sqlite / sqlite+driver URL 中提取文件路径。"""
    raw_path = unquote(parsed.path or "")
    uses_remote_host = bool(parsed.netloc and parsed.netloc not in ("localhost", ""))

    if uses_remote_host:
        database_path = f"//{parsed.netloc}{raw_path}"
    else:
        database_path = raw_path

    if database_path in ("", "/"):
        raise NonRetryableBackupError("SQLite database path is empty")
    if database_path in (":memory:", "/:memory:"):
        raise NonRetryableBackupError("SQLite in-memory database is not supported for backup")

    if database_path.startswith("/./") or database_path.startswith("/../"):
        database_path = database_path[1:]
    elif re.match(r"^/[A-Za-z]:/", database_path):
        # Windows 盘符路径，去掉 URL 解析产生的前导斜杠
        database_path = database_path[1:]
    elif database_path.startswith("//") and not uses_remote_host:
        # sqlite:////var/data.db -> /var/data.db
        database_path = database_path[1:]

    return database_path


def _collect_stderr_tail(stderr_stream, max_lines: int = PG_DUMP_STDERR_TAIL_LINES) -> list[str]:
    """流式收集 stderr 尾部，避免内存放大。"""
    if stderr_stream is None:
        return []

    lines: list[str] = []
    for line in stderr_stream:
        normalized = line.strip()
        if not normalized:
            continue
        lines.append(normalized)
        if len(lines) > max_lines:
            lines.pop(0)
    return lines


def _parse_database_url(database_url: str) -> dict:
    """解析数据库连接串并返回统一配置字典。"""
    try:
        parsed = urlparse(database_url)
        scheme = parsed.scheme.lower()

        if scheme.startswith("mysql"):
            db_type = "mysql"
            host = parsed.hostname or "localhost"
            port = parsed.port or 3306
            user = parsed.username or "root"
            password = parsed.password or ""
            database = parsed.path.lstrip("/") or "official_proj_2.0"
        elif scheme.startswith("postgresql"):
            db_type = "postgresql"
            host = parsed.hostname or "localhost"
            port = parsed.port or 5432
            user = parsed.username or "postgres"
            password = parsed.password or ""
            database = parsed.path.lstrip("/") or "official_proj_2.0"
        elif scheme.startswith("sqlite"):
            db_type = "sqlite"
            database_path = _extract_sqlite_database_path(parsed)
            return {
                "db_type": db_type,
                "database_path": database_path,
                "database": Path(database_path).stem,  # 以文件名作为备份数据库名
            }
        else:
            raise NonRetryableBackupError(f"Unsupported database type: {parsed.scheme}")

        return {
            "db_type": db_type,
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
        }

    except BackupTaskError:
        raise
    except Exception as exc:
        logger.error(f"Failed to parse database URL: {exc}")
        raise NonRetryableBackupError(f"Failed to parse database URL: {exc}") from exc


def _dump_database(db_config: dict, output_file: Path) -> None:
    """根据数据库类型分发到对应导出实现。"""
    db_type = db_config.get("db_type")

    if db_type == "mysql":
        _dump_mysql(db_config, output_file)
        return
    if db_type == "postgresql":
        _dump_postgresql(db_config, output_file)
        return
    if db_type == "sqlite":
        _dump_sqlite(db_config, output_file)
        return

    raise NonRetryableBackupError(f"Unsupported database type: {db_type}")


def _dump_mysql(db_config: dict, output_file: Path) -> None:
    """调用 `mysqldump` 导出 MySQL 数据库。"""
    try:
        cmd = [
            "mysqldump",
            f"--host={db_config['host']}",
            f"--port={db_config['port']}",
            f"--user={db_config['user']}",
            "--single-transaction",  # 保证数据一致性
            "--routines",  # 包含存储过程和函数
            "--triggers",  # 包含触发器
            "--events",  # 包含事件
            "--quick",  # 快速模式
            "--lock-tables=false",  # 不锁表
            db_config["database"],
        ]

        env = os.environ.copy()
        if db_config["password"]:
            env["MYSQL_PWD"] = db_config["password"]

        logger.info(f"Starting MySQL database export: {db_config['database']}")

        with open(output_file, "wb") as output_handle:
            subprocess.run(
                cmd,
                stdout=output_handle,
                stderr=subprocess.PIPE,
                env=env,
                check=True,
            )

        file_size = output_file.stat().st_size
        if file_size == 0:
            raise NonRetryableBackupError("Exported database file is empty")

        logger.info(
            f"MySQL database export successful: {output_file.name} ({file_size / 1024 / 1024:.2f} MB)"
        )

    except subprocess.CalledProcessError as exc:
        error_msg = (
            exc.stderr.decode(errors="replace") if isinstance(exc.stderr, (bytes, bytearray)) else str(exc)
        )
        _raise_dump_error("mysqldump", error_msg)
    except FileNotFoundError as exc:
        raise NonRetryableBackupError("mysqldump command not found") from exc
    except BackupTaskError:
        raise
    except Exception as exc:
        _raise_unexpected_dump_error("MySQL", exc)


def _dump_postgresql(db_config: dict, output_file: Path) -> None:
    """调用 `pg_dump` 导出 PostgreSQL 数据库。"""
    try:
        cmd = [
            "pg_dump",
            f"--host={db_config['host']}",
            f"--port={db_config['port']}",
            f"--username={db_config['user']}",
            "--no-password",  # 不提示输入密码
            "--clean",  # 包含清理命令
            "--if-exists",  # 若存在则先删除
            "--create",  # 包含创建数据库命令
            db_config["database"],
        ]

        env = os.environ.copy()
        if db_config["password"]:
            env["PGPASSWORD"] = db_config["password"]

        logger.info(f"Starting PostgreSQL database export: {db_config['database']}")

        with open(output_file, "wb") as output_handle:
            process = subprocess.Popen(
                cmd,
                stdout=output_handle,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            stderr_tail = _collect_stderr_tail(process.stderr)
            return_code = process.wait()

        if return_code != 0:
            error_msg = "\n".join(stderr_tail) if stderr_tail else f"pg_dump exited with code {return_code}"
            _raise_dump_error("pg_dump", error_msg)

        file_size = output_file.stat().st_size
        if file_size == 0:
            raise NonRetryableBackupError("Exported database file is empty")

        logger.info(
            f"PostgreSQL database export successful: {output_file.name} ({file_size / 1024 / 1024:.2f} MB)"
        )

    except FileNotFoundError as exc:
        raise NonRetryableBackupError("pg_dump command not found") from exc
    except BackupTaskError:
        raise
    except Exception as exc:
        _raise_unexpected_dump_error("PostgreSQL", exc)


def _dump_sqlite(db_config: dict, output_file: Path) -> None:
    """调用 `sqlite3 .dump` 导出 SQLite 数据库。"""
    try:
        database_path = Path(db_config["database_path"])

        if not database_path.exists():
            raise NonRetryableBackupError(f"SQLite database file does not exist: {database_path}")

        logger.info(f"Starting SQLite database export: {database_path}")

        cmd = [
            "sqlite3",
            str(database_path),
            ".dump",
        ]

        with open(output_file, "wb") as output_handle:
            subprocess.run(
                cmd,
                stdout=output_handle,
                stderr=subprocess.PIPE,
                check=True,
            )

        file_size = output_file.stat().st_size
        if file_size == 0:
            raise NonRetryableBackupError("Exported database file is empty")

        logger.info(
            f"SQLite database export successful: {output_file.name} ({file_size / 1024 / 1024:.2f} MB)"
        )

    except subprocess.CalledProcessError as exc:
        error_msg = (
            exc.stderr.decode(errors="replace") if isinstance(exc.stderr, (bytes, bytearray)) else str(exc)
        )
        _raise_dump_error("sqlite3", error_msg)
    except FileNotFoundError as exc:
        raise NonRetryableBackupError("sqlite3 command not found") from exc
    except BackupTaskError:
        raise
    except Exception as exc:
        _raise_unexpected_dump_error("SQLite", exc)


def _compress_file(input_file: Path, output_file: Path) -> None:
    """将 SQL 文件压缩为 gzip 归档文件。"""
    try:
        logger.info(f"Starting file compression: {input_file.name}")

        with open(input_file, "rb") as input_handle:
            with gzip.open(output_file, "wb", compresslevel=6) as output_handle:
                output_handle.writelines(input_handle)

        original_size = input_file.stat().st_size
        compressed_size = output_file.stat().st_size
        compression_ratio = (1 - compressed_size / original_size) * 100

        logger.info(
            f"Compression complete: {output_file.name} "
            f"({compressed_size / 1024 / 1024:.2f} MB, "
            f"compression ratio: {compression_ratio:.1f}%)"
        )

    except OSError as exc:
        raise RetryableBackupError(f"Error compressing file: {exc}") from exc
    except Exception as exc:
        raise NonRetryableBackupError(f"Error compressing file: {exc}") from exc


def _cleanup_old_backups(backup_dir: Path, database_name: str, retention_days: int) -> None:
    """按保留天数清理过期备份文件。"""
    if retention_days <= 0:
        logger.info("Retention days <= 0, skipping cleanup")
        return

    try:
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        logger.info(f"Starting cleanup of backup files before {cutoff_date.strftime('%Y-%m-%d')}")

        escaped_name = glob.escape(database_name)
        pattern = f"{escaped_name}_backup_*.sql.gz"
        backup_files = list(backup_dir.glob(pattern))

        if not backup_files:
            logger.info("No backup files found")
            return

        files_to_delete = []
        for backup_file in backup_files:
            file_mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)
            if file_mtime < cutoff_date:
                files_to_delete.append(backup_file)

        if not files_to_delete:
            logger.info("No old backup files to clean up")
            return

        logger.info(f"Found {len(files_to_delete)} old backup files to delete")

        success_count = 0
        for file_to_delete in files_to_delete:
            try:
                file_to_delete.unlink()
                logger.info(f"Deleted old backup file: {file_to_delete.name}")
                success_count += 1
            except Exception as exc:
                logger.error(f"Failed to delete file {file_to_delete.name}: {exc}")

        logger.info(f"Cleanup complete: successfully deleted {success_count} files")

    except Exception as exc:
        logger.error(f"Error cleaning up old backup files: {exc}", exc_info=True)


@celery_app.task(
    name="backup_database_task",
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 失败后 5 分钟重试
    time_limit=3600,  # 硬超时 1 小时
    soft_time_limit=3300,  # 软超时 55 分钟
)
@with_db_init
def backup_database_task(
    self,
    database_name: Optional[str] = None,
    retention_days: int = 30,
    backup_dir: Optional[str] = None,
) -> dict:
    """执行数据库备份任务并返回结果摘要。"""
    sql_file = None
    gz_file = None
    database_for_result = database_name.strip() if isinstance(database_name, str) else "unknown"

    try:
        database_url = settings.database.DATABASE_URL
        db_config = _parse_database_url(database_url)

        if database_name:
            db_config["database"] = database_name

        dump_db_name = _normalize_database_name(db_config["database"])
        backup_db_name = _to_backup_file_name(dump_db_name)
        db_config["database"] = dump_db_name
        database_for_result = dump_db_name

        logger.info(
            f"Starting database backup: db={dump_db_name}, file_prefix={backup_db_name}"
        )

        backup_path = _resolve_backup_dir(backup_dir)
        backup_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sql_file = backup_path / f"{backup_db_name}_backup_{timestamp}.sql"
        gz_file = backup_path / f"{backup_db_name}_backup_{timestamp}.sql.gz"

        _dump_database(db_config, sql_file)
        _compress_file(sql_file, gz_file)

        sql_file.unlink(missing_ok=True)

        if retention_days > 0:
            try:
                _cleanup_old_backups(backup_path, backup_db_name, retention_days)
            except Exception as cleanup_error:
                # 清理失败不影响备份主流程成功
                logger.warning(f"Failed to clean up old backup files: {cleanup_error}")

        backup_file_size = gz_file.stat().st_size
        result = {
            "success": True,
            "database": dump_db_name,
            "backup_file": str(gz_file),
            "file_size_mb": round(backup_file_size / 1024 / 1024, 2),
            "timestamp": timestamp,
            "retention_days": retention_days,
            "message": "Backup successful",
        }

        logger.info(f"✅ Backup complete: {gz_file} ({result['file_size_mb']} MB)")
        return result

    except Exception as exc:
        logger.error(f"Backup failed: {exc}", exc_info=True)

        for file in [sql_file, gz_file]:
            if file and file.exists():
                try:
                    file.unlink()
                    logger.debug(f"Cleaned up temporary file: {file}")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to clean up temporary file {file}: {cleanup_error}")

        if _is_retryable_exception(exc) and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=300)

        return {
            "success": False,
            "database": database_for_result,
            "error": _trim_error_message(str(exc)),
            "message": "Backup failed",
        }
