"""주간 벤치: 게이트 로그 감사 (LOOP.md 벤치마크 삼각측량 — 주간 항목).

읽기 전용 — localhost:8000 MCP(list_events)로 ADD 이벤트를 수집해
(1) 이벤트 유형 센서스, (2) metadata.accounting 전수 합산 위에서
단계별 탈락 비율(과압축 감시)을 계산한다. 실DB에는 아무것도 쓰지 않는다 (원칙 3·4).

P7(b)의 판정 도구: 사이클 7 기준선은 분모가 표본 1(게이트 로그 행)이었다.
사이클 16의 ADD 회계 배포 후에는 카운터 합이 전수 분모가 된다 — 게이트 로그는
이벤트당 50건 샘플이므로 분모의 권위는 카운터에 있다(로그=내용, 카운터=전수).
배포 전 이벤트에는 accounting이 없으므로 coverage를 함께 보고한다 — coverage가
1.0 미만이면 비율은 회계가 있는 부분창만 대표한다.

단위 규율(정직 원칙): 메시지·문장·사실·저장쌍은 서로 다른 단위이므로 하나의
혼합 비율로 섞지 않고, 단계마다 같은 단위의 분모로 비율을 낸다. 원격 프로바이더
추출 이벤트는 문장 불투명(provider_extractions 마커)이라 메시지·문장 단계 비율은
로컬 추출 이벤트만 대표한다.

사용: .venv/bin/python research/devloop/scripts/gate_audit.py [--days 30]
"""

import argparse
import datetime as dt
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from forget.store import add_accounting_violations  # noqa: E402

MCP_URL = "http://localhost:8000/mcp/forget/http/junghunkim"

# identity_violations는 목록이라 합산 제외 — 나머지는 전부 계수기.
COUNTER_KEYS = [
    "messages_in", "empty_messages", "ack_messages_dropped",
    "sentences_seen", "fragments_dropped", "gate_dropped",
    "facts_raw", "facts_extracted", "batch_deduped",
    "instruction_filtered", "facts_out",
    "scope_deduped", "sanitize_dropped", "records_kept",
    "fact_scope_pairs", "duplicate_skipped", "memories_created",
    "provider_extractions",
]


def mcp_call(name: str, arguments: dict):
    """MCP HTTP 엔드포인트로 tools/call — cycle-prompt.md의 curl 폴백과 동일 경로."""
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    ).encode()
    req = urllib.request.Request(
        MCP_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        rpc = json.load(r)
    return json.loads(rpc["result"]["content"][0]["text"])


def fetch_events(cutoff: str, max_pages: int = 500):
    """cutoff(YYYY-MM-DD) 이후 이벤트를 최신순 페이지네이션으로 수집."""
    events = []
    page = 1
    while page <= max_pages:
        data = mcp_call("list_events", {"page": page, "page_size": 100})
        results = data.get("results", [])
        if not results:
            break
        events.extend(results)
        oldest = min(e["created_at"][:10] for e in results)
        if oldest < cutoff or not data.get("next"):
            break
        page += 1
    return [e for e in events if e["created_at"][:10] >= cutoff], page


def _ratio(num: int, den: int):
    return round(num / den, 4) if den else None


def aggregate_accounting(add_events: list) -> dict:
    """ADD 이벤트들의 metadata.accounting을 전수 합산해 단계별 탈락 비율을 낸다.

    보존식 위반은 이벤트에 찍힌 스탬프를 믿지 않고 add_accounting_violations로
    재계산한다 — 감사 도구가 피감사 코드의 자기 채점을 재사용하되, 스탬프 누락은
    잡아낸다(스탬프는 있는데 재계산 위반이 없으면 코드 버전 차이 신호).
    """
    totals: Counter = Counter()
    with_acc = 0
    recomputed = []
    stamped = []
    for e in add_events:
        acc = (e.get("metadata") or {}).get("accounting")
        if not isinstance(acc, dict) or not acc:
            continue
        with_acc += 1
        for key in COUNTER_KEYS:
            value = acc.get(key)
            if isinstance(value, (int, float)):
                totals[key] += int(value)
        if acc.get("identity_violations"):
            stamped.append(e.get("id"))
        violations = add_accounting_violations(acc)
        if violations:
            recomputed.append({"event": e.get("id"), "violations": violations})

    n = totals  # 가독용 별칭
    counted_refusals = (
        n["gate_dropped"] + n["ack_messages_dropped"] + n["sanitize_dropped"]
    )
    return {
        "add_events": len(add_events),
        "events_with_accounting": with_acc,
        "coverage": _ratio(with_acc, len(add_events)),
        "denominator_authority": "counters (gate_log rows are sampled, 50/event)",
        "totals": {k: n[k] for k in COUNTER_KEYS if n[k]},
        "counted_refusals": counted_refusals,
        "identity_violations_recomputed": recomputed,
        "identity_violations_stamped_events": stamped,
        "stage_ratios": {
            # 단계마다 같은 단위의 분모 — 혼합 비율은 내지 않는다.
            "message_drop": _ratio(n["empty_messages"] + n["ack_messages_dropped"], n["messages_in"]),
            "gate_refusal": _ratio(n["gate_dropped"], n["sentences_seen"]),
            "fragment_drop": _ratio(n["fragments_dropped"], n["sentences_seen"]),
            "extraction_dedup": _ratio(n["batch_deduped"], n["facts_raw"]),
            "instruction_filter": _ratio(n["instruction_filtered"], n["facts_extracted"]),
            "record_drop": _ratio(n["scope_deduped"] + n["sanitize_dropped"], n["facts_out"]),
            "storage_dedup": _ratio(n["duplicate_skipped"], n["fact_scope_pairs"]),
            "retention": _ratio(n["memories_created"], n["fact_scope_pairs"]),
        },
        "notes": [
            "coverage < 1.0이면 비율은 회계가 있는 부분창만 대표 (배포 전 이벤트는 accounting 없음)",
            "provider_extractions > 0이면 메시지·문장 단계 비율은 로컬 추출 이벤트만 대표",
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    args = ap.parse_args()

    today = dt.date.today()
    cutoff = (today - dt.timedelta(days=args.days)).isoformat()

    events, pages = fetch_events(cutoff)
    by_type = Counter(e["event_type"] for e in events)
    add_events = [e for e in events if e["event_type"] == "ADD"]
    adds_by_day = Counter(e["created_at"][:10] for e in add_events)

    report = {
        "window": {"from": cutoff, "to": today.isoformat()},
        "pages_fetched": pages,
        "events_total_in_window": len(events),
        "by_type": dict(by_type),
        "add_events": by_type.get("ADD", 0),
        "adds_by_day": dict(sorted(adds_by_day.items())),
        "accounting": aggregate_accounting(add_events),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
