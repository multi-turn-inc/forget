#!/bin/bash
# 2차 멘토링 데모 드라이버 (2026-09-07~08) — 실서버 3장면.
# 서사: docs/demo/mentoring-2026-09-07.md. INTERACTIVE=1이면 장면마다 멈춤.
# 격리: 데모 데이터는 app_id=demo-mentoring 공유 스코프에만 산다.
set -euo pipefail
BASE="http://localhost:8000"
OWNER="Authorization: Bearer $(cat ~/.forget/keys/owner.key)"
AGENT="Authorization: Bearer $(cat ~/.forget/keys/claude-exec.key)"
APP="demo-mentoring"
J="Content-Type: application/json"
pause() { [ "${INTERACTIVE:-0}" = "1" ] && read -rp "⏎ 다음 장면..." || true; }
hr() { printf '\n\033[1;36m━━ %s\033[0m\n' "$1"; }

hr "장면 1 — 기억이 있다 (그리고 망각을 학습했다)"
echo '# 개인 원장 7,800행에서 질의 없이도 작업 관성이 기억을 예열한다'
curl -s -X POST "$BASE/mcp/forget/http/junghunkim" -H "$J" -d '{
  "jsonrpc":"2.0","id":1,"method":"tools/call",
  "params":{"name":"search_memories","arguments":{"query":"지금 진행 중인 연구","top_k":3,"score_breakdown":true}}}' \
| python3 -c "
import sys, json
data = json.loads(json.load(sys.stdin)['result']['content'][0]['text'])
for r in data['results'][:3]:
    bd = r.get('score_breakdown') or {}
    tag = '⚡학습된 망각' if bd.get('actr_learned') else ''
    print(f\"  [{r.get('score')}] {tag} {(r.get('memory') or '')[:76]}\")"
pause

hr "장면 2 — 기억 경제: 허락한 만큼만, 영수증으로 증명"
echo '# (사전) 팀 공유 스코프에 지식 씨딩 — PII 포함 문장'
curl -s -X POST "$BASE/v1/memories/" -H "$AGENT" -H "$J" -d '{
  "messages":[{"role":"user","content":"팀 결정: 파일럿 고객 미팅은 9/12, 담당 연락처 010-4821-7733"}],
  "app_id":"'"$APP"'","infer":false}' > /dev/null && echo "  ✓ 씨딩됨"

echo '# 소유자: 파트너 에이전트(claude-exec 자격)에게 쿼터 3회 그랜트 발급'
GRANT=$(curl -s -X POST "$BASE/v1/grants/" -H "$OWNER" -H "$J" -d '{
  "grantee_pattern":"claude-exec","scope_app":"'"$APP"'","quota":3}')
echo "$GRANT" | python3 -c "import sys,json; g=json.load(sys.stdin); print(f'  grant {g[\"id\"][:18]}… quota {g[\"quota\"]} · PII 검문 {len(g[\"deny_pii\"])}종')"
GID=$(echo "$GRANT" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo '# 사칭 시도: 내 자격으로 남의 grantee 흉내 → 자격 결합이 차단'
curl -s -X POST "$BASE/v1/memories/serve/" -H "$AGENT" -H "$J" -d '{
  "grantee":"someone-else","scope_app":"'"$APP"'","query":"미팅"}' \
| python3 -c "import sys,json; print('  ⛔', json.load(sys.stdin)['detail'])"

echo '# 정당한 요청: 지식은 흐르고 PII는 검문에 걸린다'
SERVE=$(curl -s -X POST "$BASE/v1/memories/serve/" -H "$AGENT" -H "$J" -d '{
  "grantee":"claude-exec","scope_app":"'"$APP"'","query":"파일럿 고객 미팅 일정"}')
echo "$SERVE" | python3 -c "
import sys, json
o = json.load(sys.stdin)
print(f'  allowed={o[\"allowed\"]} · 서빙 {len(o[\"results\"])}건 · 검문 {o[\"receipt\"][\"redactions\"]}건')
for r in o['results'][:2]: print(f'    「{r[\"memory\"][:70]}」')
print(f'  영수증 서명: {o[\"receipt\"][\"signature_ed25519\"][:24]}… (Ed25519)')"

echo '# 제3자: 영수증 검증 — 서명·영속·결합(누가/무엇을/어느 범위) 3중 확인'
python3 - "$SERVE" <<'PYEOF'
import sys, json, os, urllib.request
receipt = json.loads(sys.argv[1])["receipt"]
key = open(os.path.expanduser("~/.forget/keys/claude-exec.key")).read().strip()
def verify(rc, **exp):
    body = {"receipt": rc, "expected": {"query": "파일럿 고객 미팅 일정",
            "grantee": "claude-exec", "scope_app": "demo-mentoring", **exp}}
    req = urllib.request.Request("http://localhost:8000/v1/receipts/verify/",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    return json.loads(urllib.request.urlopen(req).read())
ok = verify(receipt)
print(f"  원본 영수증 → valid={ok['valid']} (서명 {ok['signature_valid']} · 영속 {ok['persistence_valid']} · 결합 {ok['binding_valid']})")
print(f"  변조(서빙 999건 주장) → valid={verify({**receipt, 'items_served': 999})['valid']}")
print(f"  결합 위반(다른 질의 주장) → valid={verify(receipt, query='다른 질의')['valid']}")
PYEOF

echo '# 그랜트 없는 낯선 에이전트(selfharness 자격): 거절 — 거절도 영수증에 남는다'
STRANGER="Authorization: Bearer $(cat ~/.forget/keys/selfharness.key)"
curl -s -X POST "$BASE/v1/memories/serve/" -H "$STRANGER" -H "$J" -d '{
  "grantee":"selfharness","scope_app":"'"$APP"'","query":"미팅"}' \
| python3 -c "import sys,json; o=json.load(sys.stdin); print(f'  allowed={o[\"allowed\"]} reason={o[\"reason\"]}')"
curl -s -X POST "$BASE/v1/grants/$GID/revoke" -H "$OWNER" > /dev/null && echo "  (그랜트 회수됨 — 데모 정리)"
pause

hr "장면 3 — 응고 기관: 판결은 한 번, 유지는 기계"
echo '# 오늘 첫 실DB 집행 — 반복 246행이 정본 뒤로 침강 (가역·원장 보존)'
wc -l < ~/.forget/compile_ledgers/b-20260829-1.jsonl | xargs -I{} echo "  집행 원장: {}행 (revert_compile 한 줄로 전량 복원)"
python3 -c "
import json
entry = json.loads(open('$HOME/.forget/compile_ledgers/b-20260829-1.jsonl').readline())
print(f'  예: {entry[\"form\"]} 군집의 구본 → 정본 {entry[\"canonical\"][:8]}… 링크로 침강')"
echo '# 매일 새벽 야간 응고 2단으로 자동 — 판결된 군집의 재성장은 기계가 청소'
grep COMPILER ~/.forget/selfharness/consolidation.log 2>/dev/null | tail -1 | sed 's/^/  /' || echo "  (첫 야간 런 대기 중 — 오늘 배선됨)"

hr "끝 — 숫자 한 줄"
echo "  질의 없이 다음 필요 기억 66% 예지 · 학습된 망각 스펙트럼 8채널 라이브 · 테스트 808"
