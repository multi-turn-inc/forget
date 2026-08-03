"""Project-scoped memory layer: detection, layering, and the write stamp.

The design bet (2026-08-01): a scope the user has to declare is a scope that
fails, so the boundary is derived from cwd. These tests pin the two ways that
bet can break — a repo that resolves to two different keys (fragmentation
again) and a layer filter that hides memories that should stay visible
(the day-one regression: every existing memory predates the tag).
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
from pathlib import Path

import pytest

from forget.store import matches_filters, validate_filters

HOOKS_DIR = Path(__file__).resolve().parents[1] / "hooks"


def _load(name: str):
    sys.path.insert(0, str(HOOKS_DIR))
    spec = importlib.util.spec_from_file_location(name, HOOKS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


project_mod = _load("forget_project")


@pytest.fixture(autouse=True)
def _no_user_config(monkeypatch, tmp_path):
    """The real ~/.forget/projects.json must not steer the test suite."""
    monkeypatch.setattr(project_mod, "CONFIG_PATH", str(tmp_path / "absent.json"))


def _repo(root: Path, origin: str | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    git = root / ".git"
    git.mkdir()
    config = "[core]\n\trepositoryformatversion = 0\n"
    if origin:
        config += f'[remote "origin"]\n\turl = {origin}\n\tfetch = +refs/heads/*\n'
    (git / "config").write_text(config, encoding="utf-8")
    return root


def _worktree(main_repo: Path, path: Path, name: str) -> Path:
    """A linked worktree: .git is a file pointing into the main repo."""
    worktrees = main_repo / ".git" / "worktrees" / name
    worktrees.mkdir(parents=True)
    path.mkdir(parents=True)
    (path / ".git").write_text(f"gitdir: {worktrees}\n", encoding="utf-8")
    return path


# --- detection ---------------------------------------------------------------

def test_remote_name_wins_over_directory_name(tmp_path):
    repo = _repo(tmp_path / "checkout-with-odd-name", "https://github.com/multi-turn-inc/forget.git")
    assert project_mod.project_key_for_path(str(repo)) == "forget"


def test_worktree_and_main_clone_share_one_key(tmp_path):
    """The trap flagged at design time, and live in this very session: an Orca
    worktree named after a throwaway branch topic must not become its own
    project."""
    main = _repo(tmp_path / "Documents" / "forget", "git@github.com:multi-turn-inc/forget.git")
    tree = _worktree(main, tmp_path / "orca" / "workspaces" / "내-프롬프트를-공유하기-싫어", "topic")
    assert project_mod.project_key_for_path(str(tree)) == "forget"
    assert project_mod.project_key_for_path(str(main)) == "forget"


def test_monorepo_subdirectory_keys_to_the_repo(tmp_path):
    repo = _repo(tmp_path / "mono", "https://github.com/acme/mono.git")
    deep = repo / "packages" / "web" / "src"
    deep.mkdir(parents=True)
    assert project_mod.project_key_for_path(str(deep)) == "mono"


def test_remoteless_repo_uses_repo_directory_not_cwd(tmp_path):
    repo = _repo(tmp_path / "Quant")
    deep = repo / "research" / "backtests"
    deep.mkdir(parents=True)
    assert project_mod.project_key_for_path(str(deep)) == "quant"


def test_home_and_plain_directories(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    assert project_mod.project_key_for_path(str(tmp_path / "home")) is None
    loose = tmp_path / "home" / "scratchpad"
    loose.mkdir()
    assert project_mod.project_key_for_path(str(loose)) == "scratchpad"
    assert project_mod.project_key_for_path("") is None


def test_alias_and_ignore_config(tmp_path, monkeypatch):
    config = tmp_path / "projects.json"
    config.write_text(
        json.dumps({"aliases": {"github.com/acme/forget": "acme-forget"}, "ignore": ["scratchpad"]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(project_mod, "CONFIG_PATH", str(config))
    collision = _repo(tmp_path / "forget", "https://github.com/acme/forget.git")
    assert project_mod.project_key_for_path(str(collision)) == "acme-forget"
    monkeypatch.setenv("HOME", str(tmp_path))
    loose = tmp_path / "scratchpad"
    loose.mkdir()
    assert project_mod.project_key_for_path(str(loose)) is None


def test_submodule_is_its_own_project(tmp_path):
    """A submodule's .git file points at parent/.git/modules/<name>, which has
    the submodule's own remote — it keys to itself, not the parent."""
    parent = _repo(tmp_path / "parent", "https://github.com/acme/parent.git")
    moddir = parent / ".git" / "modules" / "lib"
    moddir.mkdir(parents=True)
    (moddir / "config").write_text('[remote "origin"]\n\turl = https://github.com/acme/lib.git\n', encoding="utf-8")
    sub = parent / "vendor" / "lib"
    sub.mkdir(parents=True)
    (sub / ".git").write_text(f"gitdir: {moddir}\n", encoding="utf-8")
    assert project_mod.project_key_for_path(str(sub)) == "lib"


def test_relative_gitdir_pointer_resolves(tmp_path):
    """git writes worktree pointers relative sometimes — must still collapse."""
    main = _repo(tmp_path / "main2", "https://github.com/acme/main2.git")
    (main / ".git" / "worktrees" / "wt").mkdir(parents=True)
    checkout = tmp_path / "wt-checkout"
    checkout.mkdir()
    (checkout / ".git").write_text("gitdir: ../main2/.git/worktrees/wt\n", encoding="utf-8")
    assert project_mod.project_key_for_path(str(checkout)) == "main2"


def test_symlinked_cwd_and_nested_repo(tmp_path):
    real = _repo(tmp_path / "realrepo", "https://github.com/acme/realrepo.git")
    link = tmp_path / "link"
    link.symlink_to(real)
    assert project_mod.project_key_for_path(str(link)) == "realrepo"
    inner = _repo(tmp_path / "realrepo" / "experiments" / "inner", "https://github.com/acme/inner.git")
    assert project_mod.project_key_for_path(str(inner)) == "inner"  # closest .git wins


def test_broken_git_pointer_falls_back_to_directory_name(tmp_path):
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / ".git").write_text("not a gitdir pointer", encoding="utf-8")
    assert project_mod.project_key_for_path(str(broken)) == "broken"  # fail-open, no crash


def test_container_directories_are_not_projects(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    for name in ("Documents", "workspaces", "src"):
        loose = tmp_path / name
        loose.mkdir()
        assert project_mod.project_key_for_path(str(loose)) is None, name


def test_repo_identity_normalizes_url_shapes():
    for url in (
        "https://github.com/multi-turn-inc/forget.git",
        "git@github.com:multi-turn-inc/forget.git",
        "ssh://git@github.com/multi-turn-inc/forget",
        "https://github.com/multi-turn-inc/forget/",
    ):
        assert project_mod.repo_identity(url) == "github.com/multi-turn-inc/forget", url


# --- layering ----------------------------------------------------------------

def _row(**metadata) -> dict:
    return {"id": "m1", "memory": "x", "metadata": metadata}


def test_layer_filter_is_a_valid_filter_expression():
    validate_filters(project_mod.layered_filter("forget"))  # raises on a bad key


def test_layer_filter_shows_this_project_global_and_untagged():
    filters = project_mod.layered_filter("forget")
    assert matches_filters(_row(project="forget", scope_layer="project"), filters)
    assert matches_filters(_row(), filters)  # predates layering → global
    assert matches_filters(_row(project="quant", scope_layer="global"), filters)


def test_layer_filter_silences_another_projects_rows():
    filters = project_mod.layered_filter("forget")
    assert not matches_filters(_row(project="quant", scope_layer="project"), filters)


def test_no_project_means_no_filter():
    assert project_mod.layered_filter(None) is None


def test_classifier_promotes_facts_about_the_user():
    assert project_mod.classify_layer("나는 tabs보다 spaces를 선호해") == "global"
    assert project_mod.classify_layer("모든 프로젝트에서 커밋 메시지는 한국어로") == "global"
    assert project_mod.classify_layer("I always prefer trunk-based development") == "global"
    assert project_mod.classify_layer("이 레포는 pytest 대신 unittest를 쓴다") == "project"
    assert project_mod.classify_layer("0.3.7 릴리스는 시맨틱 기본값으로 나갔다") == "project"


def test_cross_project_requests_are_recognized():
    assert project_mod.wants_cross_project("다른 프로젝트에서 뭐 했더라?")
    assert project_mod.wants_cross_project("across all projects, what did I decide?")
    assert project_mod.wants_cross_project("모든 프로젝트 통틀어 열린 루프 보여줘")
    assert not project_mod.wants_cross_project("이 프로젝트 릴리스 상태 알려줘")


def test_classifier_misfires_found_in_probe_stay_fixed():
    """2026-08-01 probe session: the three v1 misclassifications, pinned."""
    # repo-context anchor outranks the 내가+선호 user pattern
    assert project_mod.classify_layer("이 레포는 내가 선호하는 패턴대로 정리했다") == "project"
    # English universal quantifier over projects is a global fact
    assert project_mod.classify_layer("all projects should use ruff") == "global"
    # "프로젝트 전체" means THIS project entire — not a boundary crossing
    assert not project_mod.wants_cross_project("프로젝트 전체 테스트 돌려줘")
    assert not project_mod.wants_cross_project("레포 전체 검색해줘")


# --- write stamp (PreToolUse) ------------------------------------------------

def _tag(monkeypatch, capsys, hook_input: dict) -> dict | None:
    module = _load("forget_projecttag")
    monkeypatch.setattr(module, "project_key_for_path", lambda path: "forget")
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(hook_input)))
    module.main()
    out = capsys.readouterr().out.strip()
    return json.loads(out) if out else None


def test_add_memory_gets_project_and_layer(monkeypatch, capsys):
    payload = _tag(
        monkeypatch,
        capsys,
        {
            "tool_name": "mcp__forget__add_memory",
            "cwd": "/somewhere/forget",
            "tool_input": {"text": "이 레포는 uv로 테스트를 돌린다", "infer": False},
        },
    )
    updated = payload["hookSpecificOutput"]["updatedInput"]
    assert payload["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert "permissionDecision" not in payload["hookSpecificOutput"]  # provenance only
    assert updated["metadata"] == {
        "project": "forget",
        "scope_layer": "project",
        "project_tagger": "cwd-git-v1",
    }
    assert updated["infer"] is False  # rest of the input survives untouched


def test_record_task_state_gets_top_level_project(monkeypatch, capsys):
    payload = _tag(
        monkeypatch,
        capsys,
        {
            "tool_name": "mcp__forget__record_task_state",
            "cwd": "/somewhere/forget",
            "tool_input": {"task_id": "release-0.3.8", "status": "in_progress", "summary": "릴리스 준비"},
        },
    )
    updated = payload["hookSpecificOutput"]["updatedInput"]
    assert updated["project"] == "forget"
    assert "metadata" not in updated  # task ledger takes the key top-level
    assert _tag(
        monkeypatch,
        capsys,
        {
            "tool_name": "mcp__forget__record_task_state",
            "cwd": "/x",
            "tool_input": {"task_id": "t", "summary": "s", "project": "quant"},
        },
    ) is None  # explicit caller outranks detection


def test_user_fact_is_stamped_global(monkeypatch, capsys):
    payload = _tag(
        monkeypatch,
        capsys,
        {
            "tool_name": "mcp__forget__add_memory",
            "cwd": "/somewhere/forget",
            "tool_input": {"messages": [{"role": "user", "content": "나는 아침에 회의를 싫어해"}]},
        },
    )
    assert payload["hookSpecificOutput"]["updatedInput"]["metadata"]["scope_layer"] == "global"


def test_explicit_project_and_other_tools_untouched(monkeypatch, capsys):
    assert _tag(
        monkeypatch,
        capsys,
        {
            "tool_name": "mcp__forget__add_memory",
            "cwd": "/x",
            "tool_input": {"text": "t", "metadata": {"project": "quant"}},
        },
    ) is None
    assert _tag(monkeypatch, capsys, {"tool_name": "Bash", "cwd": "/x", "tool_input": {"command": "ls"}}) is None


def test_scope_switch_off_disables_the_stamp(monkeypatch, capsys):
    monkeypatch.setenv("FORGET_PROJECT_SCOPE", "off")
    assert _tag(
        monkeypatch, capsys, {"tool_name": "mcp__forget__add_memory", "cwd": "/x", "tool_input": {"text": "t"}}
    ) is None


# --- read side ---------------------------------------------------------------

def _recall(monkeypatch, tmp_path, prompt: str, results=None):
    module = _load("forget_turnrecall")
    monkeypatch.setattr(module, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(module, "project_key_for_path", lambda path: "forget")
    sent: dict = {}

    def fake_rpc(name, arguments, timeout=5):
        sent[name] = arguments
        return {"results": results or []}

    monkeypatch.setattr(module, "_rpc", fake_rpc)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"prompt": prompt, "session_id": "s1", "cwd": "/x"})))
    module.main()
    return sent


def test_turn_recall_scopes_to_the_current_project(monkeypatch, tmp_path):
    sent = _recall(monkeypatch, tmp_path, "릴리스 상태 어떻게 됐어?")
    assert sent["search_memories"]["filters"] == project_mod.layered_filter("forget")


def test_turn_recall_crosses_only_when_asked(monkeypatch, tmp_path, capsys):
    hits = [{"id": "m9", "score": 0.9, "memory": "Quant 백테스트 결과", "metadata": {}, "trust": {"light": "green"}}]
    sent = _recall(monkeypatch, tmp_path, "다른 프로젝트에서는 뭐 하고 있었지?", results=hits)
    assert "filters" not in sent["search_memories"]
    assert "프로젝트 경계를 넘어 검색함" in capsys.readouterr().out


def test_session_capsule_requests_the_layered_filter(monkeypatch, tmp_path, capsys):
    module = _load("forget_sessionstart")
    monkeypatch.setattr(module, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(module, "project_key_for_path", lambda path: "forget")
    captured: dict = {}

    class FakeResponse:
        def read(self):
            return json.dumps(
                {"result": {"content": [{"text": json.dumps({"capsule_text": "현재 목표: 프로젝트 층 구현"})}]}}
            ).encode()

    def fake_urlopen(request, timeout=8):
        captured.update(json.loads(request.data))
        return FakeResponse()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"cwd": "/x", "source": "startup", "session_id": "s1"})))
    module.main()
    assert captured["params"]["arguments"]["filters"] == project_mod.layered_filter("forget")
    assert "프로젝트 층: forget" in capsys.readouterr().out


# --- end to end through the real search path ---------------------------------

def _fresh_db(tmp_path):
    from forget import db as app_db
    from forget.db import init_db

    path = tmp_path / "project-layer.sqlite3"
    os.environ["MEM1_DB_PATH"] = str(path)
    app_db.DB_PATH = path
    init_db()


def _seed_two_projects():
    from forget.store import add_memories

    stamp = {"project": "forget", "scope_layer": "project"}
    other = {"project": "quant", "scope_layer": "project"}
    base = {"user_id": "me", "infer": False}
    add_memories({"messages": [{"role": "user", "content": "forget 릴리스는 시맨틱 기본값으로 나간다."}], "metadata": stamp, **base})
    add_memories({"messages": [{"role": "user", "content": "Quant 백테스트는 주 1회 동결 기준으로 돈다."}], "metadata": other, **base})
    add_memories({"messages": [{"role": "user", "content": "정훈은 어두운 테마를 선호한다."}], "metadata": {"scope_layer": "global"}, **base})
    add_memories({"messages": [{"role": "user", "content": "레이어링 이전의 기준 없는 기억."}], **base})


def test_search_holds_the_project_boundary(monkeypatch, tmp_path):
    from forget.store import search_memories

    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("MEM1_SCOPE_FALLBACK_DEFAULT", raising=False)
    _fresh_db(tmp_path)
    _seed_two_projects()
    # Over MCP the layered OR arrives entity-free, so _mcp_scoped_filters
    # merges the session's user_id alongside it — mirror that here.
    filters = {"user_id": "me", **project_mod.layered_filter("forget")}
    hits = search_memories({"query": "백테스트 주기", "filters": filters, "top_k": 10})["results"]
    texts = " ".join(str(m.get("memory")) for m in hits)
    assert "백테스트" not in texts, "the other project's rows must stay silent"
    hits = search_memories({"query": "릴리스 테마 기준", "filters": filters, "top_k": 10})["results"]
    texts = " ".join(str(m.get("memory")) for m in hits)
    assert "릴리스" in texts and "테마" in texts and "기준 없는" in texts


def test_scope_fallback_may_not_readmit_the_other_project(monkeypatch, tmp_path):
    """Fallback relaxes WHO may see a row, never a content boundary — with it
    on, quant rows must not re-enter a forget-layered search as discounted hits."""
    from forget.store import search_memories

    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    _fresh_db(tmp_path)
    _seed_two_projects()
    hits = search_memories(
        {
            "query": "백테스트 주기",
            "filters": {"user_id": "me", **project_mod.layered_filter("forget")},
            "top_k": 10,
            "scope_fallback": True,
        }
    )["results"]
    texts = " ".join(str(m.get("memory")) for m in hits)
    assert "백테스트" not in texts


def test_task_ledger_holds_the_project_boundary(monkeypatch, tmp_path):
    """The F2 cure, end to end: a Quant task must not surface as the current
    task of a forget-scoped read — while untagged (pre-layer) tasks stay
    visible everywhere."""
    from forget.store import get_task_state, record_task_state

    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    _fresh_db(tmp_path)
    record_task_state({"task_id": "quant-backtest", "status": "in_progress", "summary": "Quant 백테스트 주 1회 동결", "project": "quant-research"})
    record_task_state({"task_id": "forget-release", "status": "in_progress", "summary": "0.3.8 릴리스 큐", "project": "forget"})
    record_task_state({"task_id": "legacy-untagged", "status": "in_progress", "summary": "레이어 이전 태스크"})

    forget_view = get_task_state({"project": "forget", "limit": 20})
    ids = {r["task_id"] for r in forget_view["results"]}
    assert "forget-release" in ids and "legacy-untagged" in ids
    assert "quant-backtest" not in ids, "the other project's task must stay silent"

    cross_view = get_task_state({"limit": 20})
    ids = {r["task_id"] for r in cross_view["results"]}
    assert {"quant-backtest", "forget-release", "legacy-untagged"} <= ids, "no project → cross-project view"


def test_scope_transition_supersedes_the_untagged_epoch(monkeypatch, tmp_path):
    """Live find (2026-08-01, first real-usage test): epoch continuity keyed on
    exact scope_json let a project tag arriving fork the task — the untagged
    twin stayed open forever and leaked into every project view. A re-record
    with identical content but new scope must close the old epoch."""
    from forget.store import get_task_state, record_task_state

    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    _fresh_db(tmp_path)
    record_task_state({"task_id": "t-mig", "status": "in_progress", "summary": "동일 내용"})
    record_task_state({"task_id": "t-mig", "status": "in_progress", "summary": "동일 내용", "project": "quant-research"})

    rows = get_task_state({"task_id": "t-mig", "limit": 10})["results"]
    assert len(rows) == 1, f"one open epoch expected, got {len(rows)}"
    assert rows[0]["scope"].get("project") == "quant-research"
    forget_view = get_task_state({"project": "forget", "limit": 20})
    assert "t-mig" not in {r["task_id"] for r in forget_view["results"]}, "untagged twin must not survive the transition"


def test_scope_forks_heal_on_next_write(monkeypatch, tmp_path):
    """The pre-existing fork class (agent_id appearing/disappearing) heals the
    same way: any write closes every open epoch for the task."""
    from forget.store import get_task_state, record_task_state

    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    _fresh_db(tmp_path)
    record_task_state({"task_id": "t-fork", "status": "in_progress", "summary": "codex가 적음", "agent_id": "codex"})
    record_task_state({"task_id": "t-fork", "status": "in_progress", "summary": "claude가 적음"})
    rows = get_task_state({"task_id": "t-fork", "limit": 10})["results"]
    assert len(rows) == 1 and rows[0]["summary"] == "claude가 적음"


def test_task_metadata_passthrough_survives(monkeypatch, tmp_path):
    from forget.store import get_task_state, record_task_state

    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    _fresh_db(tmp_path)
    record_task_state({"task_id": "t1", "status": "in_progress", "summary": "s", "metadata": {"project": "forget", "note": "x"}})
    view = get_task_state({"project": "quant-research", "limit": 20})
    assert "t1" not in {r["task_id"] for r in view["results"]}, "metadata.project must scope like top-level project"


def test_fallback_still_relaxes_entity_scope(monkeypatch, tmp_path):
    """The fix must not break fallback's reason to exist: agent-shared rows
    still surface through a user-scoped search."""
    from forget.store import add_memories, search_memories

    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    _fresh_db(tmp_path)
    add_memories({"messages": [{"role": "user", "content": "배포는 main 브랜치에서만 한다."}], "agent_id": "eng", "infer": False})  # shared: no user_id
    hits = search_memories(
        {"query": "배포 브랜치", "filters": {"user_id": "me"}, "top_k": 5, "scope_fallback": True}
    )["results"]
    assert any("배포" in str(m.get("memory")) for m in hits)
