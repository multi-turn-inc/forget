"""attention_sidecar — 소스 선택 계약 (2026-09-21). 모델·원장 호출 없음.

관측: 상주 세션 (entrypoint sdk-cli) 이 몇 분마다 user 턴을 주입해 «마지막 사람 발화» 순위를 항상 이겼고,
정훈의 대화형 창 (entrypoint cli) 이 소스로 잡히지 않았다 — 하루치 log.jsonl 에 정훈 원문 0 줄.
"""
from __future__ import annotations
import glob, importlib.util, json, os, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("attention_sidecar", ROOT / "scripts" / "attention_sidecar.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)

def _line(role: str, text: str, ts: str, **kw) -> str:
    return json.dumps({"type": role, "message": {"role": role, "content": text}, "timestamp": ts, **kw}, ensure_ascii=False)

def test_last_user_ts_ignores_sdk_cli_turns(tmp_path):
    human = tmp_path / "human.jsonl"
    human.write_text("\n".join([
        _line("user", "안현준에게 보낼 메시지 간단하게 써줘", "2026-09-21T02:25:00Z", entrypoint="cli"),
        _line("user", "응 보내줘", "2026-09-21T03:12:05Z", entrypoint="cli"),
    ]) + "\n")
    body = tmp_path / "body.jsonl"
    body.write_text(_line("user", "[나]\n\n```tool\n{}\n```", "2026-09-21T03:50:42Z", entrypoint="sdk-cli") + "\n")
    assert S._last_user_ts(str(human)) > 0
    assert S._last_user_ts(str(body)) == 0.0

def test_latest_transcript_prefers_human_window_over_newer_sdk_sessions(tmp_path, monkeypatch):
    proj = tmp_path / "projects"
    (proj / "human").mkdir(parents=True)
    (proj / "body").mkdir()
    human = proj / "human" / "h.jsonl"
    human.write_text(_line("user", "응 보내줘", "2026-09-21T03:12:05Z", entrypoint="cli") + "\n")
    now = time.time()
    os.utime(human, (now - 3600, now - 3600))
    all_files = []
    for i in range(8):
        b = proj / "body" / f"b{i}.jsonl"
        b.write_text(_line("user", "[나] 자기 턴", f"2026-09-21T03:5{i}:00Z", entrypoint="sdk-cli") + "\n")
        os.utime(b, (now - i, now - i))
        all_files.append(str(b))
    all_files.append(str(human))
    all_files = sorted(all_files, key=os.path.getmtime, reverse=True)
    monkeypatch.setattr(glob, "glob", lambda p: all_files)
    monkeypatch.setitem(S.HARNESS_GLOBS, "claude", ["*"])
    assert S.latest_transcript("claude") == human
