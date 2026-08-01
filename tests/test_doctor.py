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


def test_version_newer():
    from forget.cli import _version_newer
    assert _version_newer("0.3.6", "0.3.5")
    assert not _version_newer("0.3.5", "0.3.5")
    assert not _version_newer("0.3.5", "0.3.6")
    assert _version_newer("0.10.0", "0.9.9")
    assert not _version_newer("unknown", "0.3.5")


def test_weekly_digest_counts_only(tmp_path):
    import sqlite3 as sq
    from forget.cli import weekly_digest
    path = tmp_path / "w.sqlite3"
    conn = sq.connect(path)
    conn.execute("""CREATE TABLE memories (user_id TEXT, app_id TEXT, deleted INT,
                    metadata TEXT DEFAULT '{}', created_at TEXT)""")
    conn.execute("""CREATE TABLE gate_log (user_id TEXT, reason TEXT, created_at TEXT)""")
    conn.execute("INSERT INTO memories VALUES ('u','forget',0,'{}',datetime('now','-1 day'))")
    conn.execute("INSERT INTO memories VALUES ('u','forget',0,'{\"superseded_at\":1}',datetime('now','-2 day'))")
    conn.execute("INSERT INTO memories VALUES ('u','forget',0,'{}',datetime('now','-30 day'))")  # old
    conn.execute("INSERT INTO memories VALUES ('other','forget',0,'{}',datetime('now'))")  # foreign
    conn.execute("INSERT INTO gate_log VALUES ('u','secret',datetime('now','-1 day'))")
    conn.execute("INSERT INTO gate_log VALUES ('u','secret',datetime('now','-1 day'))")
    conn.commit(); conn.close()
    d = weekly_digest(path, "u")
    assert d["added"] == 2          # this week, own pool only
    assert d["corrected"] == 1
    assert d["total"] == 3          # all-time, own pool only
    assert d["refusals"] == [("secret", 2)]


def test_stack_summary_flags_fallback():
    from forget.cli import stack_summary
    line, fb = stack_summary({"embedding_model": "deterministic-128", "llm_model": "gpt-5.5"})
    assert fb and "deterministic-128" in line
    line, fb = stack_summary({"embedding_model": "BAAI/bge-small-en-v1.5",
                              "llm_model": "rule-extractor"})
    assert fb  # extractor fallback도 잡는다
    line, fb = stack_summary({"embedding_model": "BAAI/bge-small-en-v1.5",
                              "llm_model": "claude-haiku-4-5"})
    assert not fb
