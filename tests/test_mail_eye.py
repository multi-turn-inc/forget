import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("mail_eye", Path(__file__).resolve().parents[1] / "scripts" / "mail_eye.py")
mail_eye = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mail_eye)


def test_prompt_is_read_only_and_list_only():
    p = mail_eye.build_prompt("2026-09-21 12:00")
    assert "열지 마라" in p and "조작도 하지 마라" in p and "스팸함" in p and "2026-09-21 12:00" in p


def test_busy_detects_other_aside_session():
    ps = "COMMAND\n/bin/zsh -c foo\naside --permission full-access hiworks 메일 ...\n"
    assert mail_eye.aside_busy(ps) is True
    assert mail_eye.aside_busy("COMMAND\n/Applications/Aside.app/Contents/MacOS/Aside\n") is False


def test_parse_flags_deadline_lines():
    report = (
        "받은편지함:\n"
        "- [기한] 박연진 <yjpark@dip.or.kr> | 09-14 08:54 | [DIP] 홍보물 제작 내용 요청 (~9/18) | 스팸함\n"
        "- 김정화 | 13:34 | [DIP] 2026년 국외 블록체인 시장진출 지원사업 안내 | 받은편지함\n"
        "- 신외선 | 14:54 | 컨설팅 인터뷰 일정 조사 안내 | 받은편지함\n"
        "스팸함: 없음\n"
    )
    rows = mail_eye.parse(report)
    assert len(rows) == 3
    assert rows[0]["deadline"] and rows[0]["box"] == "스팸함" and rows[0]["sender"].startswith("박연진")
    assert not rows[1]["deadline"] and not rows[2]["deadline"]


def test_compact_raw_drops_accessibility_dump_keeps_report_lines():
    dump = "\n".join(f"      - button [ref=e{i}]" for i in range(300))
    report = (
        "- [기한] 박연진 | 09-14 08:54 | [DIP] 홍보물 제작 내용 요청 (~9/18) | 스팸함\n"
        + dump + "\n"
        "신외선 | 14:54 | 컨설팅 인터뷰 일정 조사 안내 | 받은편지함\n"
        "스팸함: 없음\n"
        "created new session: NsT0wAmPOvuCljXa\n"
    )
    out = mail_eye.compact_raw(report)
    assert "[ref=" not in out
    assert "박연진" in out and "신외선" in out and "없음" in out and "created new session" in out
    assert len(out) < 4000
    assert len(mail_eye.parse(out)) == 2


def test_parse_flags_by_subject_regex_without_marker():
    rows = mail_eye.parse("- 감리 | 09:00 | 시정조치 결과 9/25까지 제출 요청 | 받은편지함")
    assert rows[0]["deadline"]
