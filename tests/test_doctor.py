"""forget-server doctor — the wiring/feel-nothing disambiguator.

Cold-start field report #2 ("잘 모르겠다"): a broken install and a working
day-one install feel identical, because hooks are fail-open. Doctor's job is
to tell them apart. These tests cover its pure judgment pieces.
"""

import sqlite3

from forget.cli import foreign_pools, hooks_wired, pool_report


def _settings(commands_by_event):
    return {
        "hooks": {
            event: [{"hooks": [{"command": cmd} for cmd in cmds]}]
            for event, cmds in commands_by_event.items()
        }
    }


def test_hooks_wired_detects_forget_commands():
    settings = _settings({
        "SessionStart": ["python3 /x/forget_sessionstart.py"],
        "UserPromptSubmit": ["other-tool --flag", "python3 /x/forget_turnrecall.py"],
        "PreCompact": ["something-else"],
    })
    wired = hooks_wired(settings)
    assert wired["SessionStart"] is True
    assert wired["UserPromptSubmit"] is True
    assert wired["PreCompact"] is False
    assert wired["SessionEnd"] is False


def test_hooks_wired_tolerates_empty_settings():
    assert all(v is False for v in hooks_wired({}).values())


def _store(tmp_path, rows):
    path = tmp_path / "t.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE memories (user_id TEXT, app_id TEXT, deleted INT DEFAULT 0)"
    )
    conn.executemany("INSERT INTO memories VALUES (?,?,?)", rows)
    conn.commit()
    conn.close()
    return path


def test_pool_report_counts_live_rows_only(tmp_path):
    path = _store(tmp_path, [
        ("junghun", "forget", 0),
        ("junghun", "forget", 0),
        ("junghun", "forget", 1),  # deleted — excluded
        ("demo", "forget", 0),
        (None, "livetest", 0),
    ])
    pools = pool_report(path)
    assert ("junghun", "forget", 2) in pools
    assert ("demo", "forget", 1) in pools
    assert ("∅", "livetest", 1) in pools


def test_foreign_pools_is_the_f4_detector(tmp_path):
    pools = [("junghun", "forget", 500), ("demo", "forget", 300), ("junghun", "offreco", 40)]
    foreign = foreign_pools(pools, user="junghun")
    assert ("junghun", "forget", 500) not in foreign
    assert len(foreign) == 2


def test_clean_store_has_no_foreign_pools():
    assert foreign_pools([("u", "forget", 10)], user="u") == []
