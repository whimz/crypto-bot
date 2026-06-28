import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from db import backup


@pytest.fixture
def temp_db(monkeypatch):
    """Point backup at a fresh temp sqlite file so _snapshot_db has something real to read."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)
    db_path.write_bytes(b"")  # sqlite3.connect() lazily creates the schema-less file is enough for .backup()
    monkeypatch.setattr(backup, "DB_PATH", str(db_path))
    try:
        yield db_path
    finally:
        db_path.unlink(missing_ok=True)


def test_backup_object_name_format():
    now = datetime(2026, 6, 28, 3, 0, 0, tzinfo=timezone.utc)
    assert backup.backup_object_name(now) == "backup-2026-06-28.db.gz"


def test_backup_object_name_defaults_to_now():
    name = backup.backup_object_name()
    assert name.startswith("backup-")
    assert name.endswith(".db.gz")


def test_run_backup_success_uploads_and_does_not_notify(temp_db, monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr(backup.boto3, "client", MagicMock(return_value=mock_client))
    notify_error = MagicMock()
    monkeypatch.setattr(backup.telegram, "notify_error", notify_error)

    backup.run_backup()

    mock_client.upload_file.assert_called_once()
    args, _ = mock_client.upload_file.call_args
    uploaded_path, bucket, object_name = args
    assert object_name.startswith("backup-") and object_name.endswith(".db.gz")
    assert Path(uploaded_path).suffix == ".gz"
    notify_error.assert_not_called()


def test_run_backup_upload_failure_notifies_telegram_and_does_not_raise(temp_db, monkeypatch):
    mock_client = MagicMock()
    mock_client.upload_file.side_effect = ClientError(
        {"Error": {"Code": "500", "Message": "boom"}}, "PutObject"
    )
    monkeypatch.setattr(backup.boto3, "client", MagicMock(return_value=mock_client))
    notify_error = MagicMock()
    monkeypatch.setattr(backup.telegram, "notify_error", notify_error)

    backup.run_backup()  # must not raise

    notify_error.assert_called_once()
    assert "Database backup failed" in notify_error.call_args[0][0]
