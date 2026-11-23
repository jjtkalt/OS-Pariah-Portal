"""Tests for scripts/backup_portal.py helpers."""

from __future__ import annotations

import os
import time
from unittest.mock import MagicMock, patch

from scripts import backup_portal as backup


def test_copy_significant_files_skips_missing_and_copies_present(tmp_path, monkeypatch):
    etc = tmp_path / "etc" / "os-pariah"
    etc.mkdir(parents=True)
    conf = etc / "os-pariah.conf"
    conf.write_text("OS_PARIAH_DB_NAME=os_pariah\n", encoding="utf-8")
    secrets = etc / "secrets"
    secrets.write_text("SECRET_KEY=test\n", encoding="utf-8")
    oidc = etc / "oidc_private.pem"
    oidc.write_text("PEM\n", encoding="utf-8")

    monkeypatch.setattr(
        backup,
        "SIGNIFICANT_FILES",
        (str(conf), str(secrets), str(tmp_path / "missing.conf")),
    )
    monkeypatch.setattr(backup, "ETC_OS_PARIAH_DIR", str(etc))

    dest = tmp_path / "run"
    dest.mkdir()
    copied = backup.copy_significant_files(dest)

    assert str(conf) in copied
    assert str(secrets) in copied
    assert str(oidc) in copied
    secrets_out = dest / "files" / secrets.as_posix().lstrip("/")
    assert secrets_out.is_file()
    assert secrets_out.stat().st_mode & 0o777 == 0o600


def test_copy_significant_dirs_copies_uploads_tree(tmp_path, monkeypatch):
    uploads = tmp_path / "var" / "lib" / "os-pariah" / "uploads" / "tickets"
    uploads.mkdir(parents=True)
    attachment = uploads / "ticket-1.bin"
    attachment.write_bytes(b"payload")

    monkeypatch.setattr(
        backup,
        "SIGNIFICANT_DIRS",
        (str(tmp_path / "var" / "lib" / "os-pariah" / "uploads"),),
    )

    dest = tmp_path / "run"
    dest.mkdir()
    copied = backup.copy_significant_dirs(dest)

    assert len(copied) == 1
    matches = list((dest / "files").rglob("ticket-1.bin"))
    assert len(matches) == 1
    assert matches[0].read_bytes() == b"payload"


def test_purge_old_backups_removes_only_expired(tmp_path):
    root = tmp_path / "portal"
    root.mkdir()
    old = root / "oldrun"
    new = root / "newrun"
    old.mkdir()
    new.mkdir()

    old_age = time.time() - (20 * 86400)
    os.utime(old, (old_age, old_age))

    removed = backup.purge_old_backups(root, retention_days=14)
    assert removed == 1
    assert not old.exists()
    assert new.exists()


def test_sync_iar_timer_interval_writes_dropin(tmp_path, monkeypatch):
    drop_dir = tmp_path / "timer.d"
    drop_file = drop_dir / "interval.conf"
    monkeypatch.setattr(backup, "IAR_TIMER_DROPIN_DIR", str(drop_dir))
    monkeypatch.setattr(backup, "IAR_TIMER_DROPIN_FILE", str(drop_file))

    with patch("scripts.backup_portal.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        backup.sync_iar_timer_interval(5)

    text = drop_file.read_text(encoding="utf-8")
    assert "OnUnitActiveSec=5d" in text
    mock_run.assert_called_once()
    assert mock_run.call_args.args[0][:2] == ["/bin/systemctl", "daemon-reload"]
