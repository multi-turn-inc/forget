"""#1 회귀: 한영 혼용 텍스트에서 기술 고유명사·약어는 person이 아니다."""
from forget.memory_engine import extract_linked_entities


def _typed(text: str) -> dict[str, tuple[str, float]]:
    return {e["normalized_entity"]: (e["entity_type"], e["confidence"]) for e in extract_linked_entities(text)}


def test_issue_table_no_longer_persons() -> None:
    # 이슈 표의 실측 오분류 항목들 — 한국어 문장 문맥 그대로
    text = "배포 파이프라인에서 Redis 캐시와 Postgres 저장소를 쓰고, CI가 깨지면 WAL 로그를 본다. E2EE는 서버 설계의 전제다."
    typed = _typed(text)
    for name in ("redis", "postgres", "ci", "wal", "e2ee"):
        if name in typed:
            kind, conf = typed[name]
            assert kind != "person", f"{name} typed as person ({conf})"


def test_acronyms_never_person_even_without_context() -> None:
    typed = _typed("HN 반응이 좋았고 YC 인터뷰가 잡혔다. OSS 공개는 다음 주다.")
    for name in ("hn", "yc", "oss"):
        if name in typed:
            assert typed[name][0] != "person", f"{name}: {typed[name]}"


def test_hashicorp_is_organization() -> None:
    typed = _typed("HashiCorp 도구로 인프라를 관리한다.")
    assert typed.get("hashicorp", ("", 0))[0] in {"organization", "technology"}


def test_real_person_still_typed_with_own_confidence() -> None:
    typed = _typed("Wooyoung moved the launch and Wooyoung owns the decision.")
    kind, conf = typed.get("wooyoung", ("", 0.0))
    assert kind == "person"
    assert conf <= 0.7, f"person confidence must come from the classifier, got {conf}"


def test_english_tech_context_gate_unchanged() -> None:
    typed = _typed("Our stack uses Fastify and the database is Postgres.")
    assert typed.get("postgres", ("", 0))[0] == "technology"
