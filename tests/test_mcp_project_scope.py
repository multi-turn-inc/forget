"""MCP 프로젝트-고정 연결의 무필터 회상 스코프 고정.

2026-08-13 검진 발견: 공용 HTTP MCP 서버는 cwd가 없어 프로젝트를 모르고,
무필터 search_memories가 사용자 스코프 전체를 회수해 타 프로젝트 기억이
섞였다(dilabv2 → forget 세션). 수리: 스코프 엔드포인트의 ?project= 키가
context["project_key"]로 들어오면, 무필터 호출에 훅의 layered_filter와
동일한 층(이 프로젝트 + 전역층 + 미태깅 레거시)을 태운다.
"""
import json

import pytest


@pytest.fixture()
def scoped_store(tmp_path, monkeypatch):
    from forget import db as app_db
    from forget.db import init_db

    path = tmp_path / "scope.sqlite3"
    monkeypatch.setenv("MEM1_DB_PATH", str(path))
    monkeypatch.setattr(app_db, "DB_PATH", path)
    init_db()

    from forget.store import add_memories

    def _add(text: str, metadata: dict | None) -> None:
        add_memories(
            {
                "messages": [{"role": "user", "content": text}],
                "user_id": "junghunkim",
                "app_id": "forget",
                "metadata": metadata or {},
                "infer": False,
            }
        )

    _add("forget 프로젝트의 회상 게이트 결정", {"project": "forget", "scope_layer": "project"})
    _add("dilabv2 빌라 입주민 서버 반입 결정", {"project": "dilabv2", "scope_layer": "project"})
    _add("층화 이전에 쓰인 미태깅 레거시 결정", {})
    _add("정훈은 반증 우선 문화를 가진 사용자다", {"scope_layer": "global"})

    # 타 사용자의 기억 — 같은 20분 창 안에서 태어났어도 어떤 경로(본검색·
    # 시간 이웃)로도 junghunkim의 회상에 나타나면 안 된다.
    add_memories(
        {
            "messages": [{"role": "user", "content": "타인의 비밀 결정 사항"}],
            "user_id": "someone-else",
            "app_id": "forget",
            "metadata": {"project": "forget", "scope_layer": "project"},
            "infer": False,
        }
    )
    return path


def _search_texts(context: dict | None) -> list[str]:
    from forget.mcp import handle_mcp_rpc

    response = handle_mcp_rpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "search_memories",
                "arguments": {"query": "결정", "top_k": 10, "threshold": 0},
            },
        },
        context=context,
    )
    body = json.loads(response["result"]["content"][0]["text"])
    return [str(item.get("memory") or "") for item in body.get("results", [])]


def test_project_pinned_connection_excludes_other_projects(scoped_store):
    texts = _search_texts({"user_id": "junghunkim", "client_name": "forget", "project_key": "forget"})
    joined = " ".join(texts)
    assert "dilabv2" not in joined
    assert "타인의 비밀" not in joined  # 시간 이웃 경로 포함 user_id 경계
    assert "forget 프로젝트" in joined  # 이 프로젝트 층
    assert "미태깅 레거시" in joined  # 층화 이전 레거시
    assert "반증 우선" in joined  # 전역층


def test_temporal_neighbor_honors_scope_filters(scoped_store):
    # 시간 인접성은 점수 특례이지 경계 특례가 아니다: 이웃 후보도 본검색과
    # 같은 필터를 통과해야 한다 (2026-08-13 검진 — 이웃 경로로 타 프로젝트·
    # 타 사용자 기억이 동승하던 구멍의 회귀 고정).
    texts = _search_texts({"user_id": "junghunkim", "client_name": "forget", "project_key": "forget"})
    joined = " ".join(texts)
    assert "dilabv2" not in joined
    assert "타인의 비밀" not in joined


def test_unpinned_connection_still_holds_user_boundary(scoped_store):
    # 프로젝트 고정이 없어도 user_id 경계는 이웃 경로에서 절대 열리지 않는다.
    texts = _search_texts({"user_id": "junghunkim", "client_name": "forget"})
    assert "타인의 비밀" not in " ".join(texts)


def test_unpinned_connection_keeps_user_scope(scoped_store):
    # 회귀 고정: project_key 없는 연결(기존 등록 URL)은 종전 동작 그대로 —
    # 사용자 스코프 전체를 회수한다.
    texts = _search_texts({"user_id": "junghunkim", "client_name": "forget"})
    joined = " ".join(texts)
    assert "dilabv2" in joined
    assert "forget 프로젝트" in joined


def test_caller_project_filter_wins_over_pinned_layer(scoped_store):
    # 호출자가 프로젝트 층을 직접 다루면(명시 metadata.project) 기본 층을 겹치지 않는다.
    from forget.mcp import handle_mcp_rpc

    response = handle_mcp_rpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "search_memories",
                "arguments": {
                    "query": "결정",
                    "top_k": 10,
                    "threshold": 0,
                    "filters": {"user_id": "junghunkim", "metadata.project": "dilabv2"},
                },
            },
        },
        context={"user_id": "junghunkim", "client_name": "forget", "project_key": "forget"},
    )
    body = json.loads(response["result"]["content"][0]["text"])
    joined = " ".join(str(item.get("memory") or "") for item in body.get("results", []))
    assert "dilabv2" in joined
    assert "forget 프로젝트" not in joined
