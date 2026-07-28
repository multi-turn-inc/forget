"""#4 회귀: 기본 DB는 사이트패키지 밖, 소유자 전용 권한으로 생성된다."""
import importlib
import os
import stat
from pathlib import Path

import forget.db as app_db


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_default_path_is_user_data_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("MEM1_DB_PATH", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(app_db, "_LEGACY_DB_PATH", tmp_path / "no-such-legacy.sqlite3")
    resolved = app_db._default_db_path()
    assert resolved == tmp_path / ".forget" / "mem1.sqlite3"
    assert "site-packages" not in str(resolved)


def test_legacy_db_is_respected(monkeypatch, tmp_path) -> None:
    legacy = tmp_path / "mem1.sqlite3"
    legacy.touch()
    monkeypatch.delenv("MEM1_DB_PATH", raising=False)
    monkeypatch.setattr(app_db, "_LEGACY_DB_PATH", legacy)
    assert app_db._default_db_path() == legacy


def test_fresh_db_created_0600_despite_umask(monkeypatch, tmp_path) -> None:
    target = tmp_path / "priv" / "mem.sqlite3"
    monkeypatch.setenv("MEM1_DB_PATH", str(target))
    old_umask = os.umask(0o022)
    try:
        conn = app_db.connect()
        conn.close()
    finally:
        os.umask(old_umask)
    assert _mode(target) == 0o600
    assert _mode(target.parent) == 0o700


def test_env_override_still_wins(monkeypatch, tmp_path) -> None:
    target = tmp_path / "elsewhere.sqlite3"
    monkeypatch.setenv("MEM1_DB_PATH", str(target))
    assert app_db.current_db_path() == target
