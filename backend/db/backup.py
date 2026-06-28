"""Daily SQLite backup: consistent snapshot via sqlite3's online backup API, gzip, upload to R2.

Old backups are NOT pruned here - rotation is configured as an R2 lifecycle rule, so this
module only ever needs to upload the latest snapshot.
"""

from __future__ import annotations

import gzip
import logging
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from config import DB_PATH, R2_ACCESS_KEY_ID, R2_BUCKET, R2_ENDPOINT, R2_SECRET_ACCESS_KEY
from notifications import telegram

logger = logging.getLogger(__name__)

BACKUP_OBJECT_PREFIX = "backup-"
BACKUP_OBJECT_SUFFIX = ".db.gz"
BACKUP_DATE_FORMAT = "%Y-%m-%d"


def backup_object_name(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{BACKUP_OBJECT_PREFIX}{now.strftime(BACKUP_DATE_FORMAT)}{BACKUP_OBJECT_SUFFIX}"


def _snapshot_db(snapshot_path: Path) -> None:
    """sqlite3's backup() API copies a transactionally-consistent view of the database, unlike
    a raw file copy which can capture a half-written page while the trading cycle is writing."""
    source = sqlite3.connect(DB_PATH)
    try:
        dest = sqlite3.connect(str(snapshot_path))
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()


def _compress(snapshot_path: Path, compressed_path: Path) -> None:
    with open(snapshot_path, "rb") as src, gzip.open(compressed_path, "wb") as dst:
        dst.writelines(src)


def _upload(compressed_path: Path, object_name: str) -> None:
    client = boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
    )
    client.upload_file(str(compressed_path), R2_BUCKET, object_name)


def run_backup() -> None:
    """Entry point for the daily APScheduler job. Never raises: failures are logged and
    sent to Telegram; a successful run only logs, to avoid a daily notification spam."""
    object_name = backup_object_name()
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / "snapshot.db"
            compressed_path = Path(tmpdir) / "snapshot.db.gz"
            _snapshot_db(snapshot_path)
            _compress(snapshot_path, compressed_path)
            _upload(compressed_path, object_name)
        logger.info("Database backup uploaded to R2: %s", object_name)
    except (BotoCoreError, ClientError, OSError, sqlite3.Error) as exc:
        logger.exception("Database backup failed: %s", object_name)
        telegram.notify_error(f"Database backup failed ({object_name}): {exc}")
