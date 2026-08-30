#!/bin/bash
# B3O E2E 상대역 키트 — 브로커(forgetMemory.ts)의 호출 모양 그대로 전 구간 관통.
# 용법: ./scripts/b3o_e2e_counterpart.sh [scope_app]  (기본: botbotbot — 클라이언트 현행 기본값)
# 검증: 그랜트 발급 → 무грант 거절 영수증 → 서빙(무 grantee·request_id 멱등) →
#       영수증 3중 검증 → human_approved 쓰기 게이트(b3o.* 스코프) → 회수.
set -euo pipefail
BASE="http://localhost:8000"
OWNER="Authorization: Bearer $(cat ~/.forget/keys/owner.key)"
B3O="Authorization: Bearer $(cat ~/.forget/keys/b3o-desktop.key)"
J="Content-Type: application/json"
SCOPE="${1:-botbotbot}"
say() { printf '%s\n' "$*"; }

say "── 0. 무그랜트 거절도 영수증인지"
curl -s -X POST "$BASE/v1/memories/serve/" -H "$B3O" -H "$J" -d '{
  "scope_app":"'"$SCOPE"'","query":"스모크","request_id":"botbotbot-denied-'$RANDOM'"}' \
| python3 -c "import sys,json; o=json.load(sys.stdin); assert o['allowed'] is False and o['receipt']['receipt_id']; print('  ✓ 거절 영수증', o['reason'])"

say "── 1. 소유자: b3o-desktop에 그랜트 (쿼터 5·만료 규약은 운영 시 필수)"
GID=$(curl -s -X POST "$BASE/v1/grants/" -H "$OWNER" -H "$J" -d '{
  "grantee_pattern":"b3o-desktop","scope_app":"'"$SCOPE"'","quota":5}' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
say "  ✓ $GID"

say "── 2. 씨딩(공유 스코프, PII 포함)"
curl -s -X POST "$BASE/v1/memories/" -H "$B3O" -H "$J" -d '{
  "messages":[{"role":"user","content":"팀 위키: 배포 창구는 매주 수요일, 담당 연락처 010-9944-2211"}],
  "app_id":"'"$SCOPE"'","infer":false}' > /dev/null && say "  ✓"

say "── 3. 브로커 모양 그대로 서빙 (grantee 없음·request_id·top_k 8)"
RID="botbotbot-$(uuidgen | tr A-Z a-z)"
SERVE=$(curl -s -X POST "$BASE/v1/memories/serve/" -H "$B3O" -H "$J" -d '{
  "scope_app":"'"$SCOPE"'","query":"배포 창구 일정","request_id":"'"$RID"'","top_k":8}')
echo "$SERVE" | python3 -c "
import sys, json
o = json.load(sys.stdin)
assert o['allowed'] is True
texts = ' '.join(r['memory'] for r in o['results'])
assert '수요일' in texts and '010-9944-2211' not in texts and '[redacted-phone]' in texts
r = o['receipt']
assert r['scope_app'] == '$SCOPE' and r['allowed'] is True and r['items_served'] == len(o['results'])
print(f\"  ✓ 서빙 {len(o['results'])}건 · 검문 {r['redactions']} · grantee(유도)={r['grantee']}\")"

say "── 4. request_id 멱등 (쿼터 재소모 없어야)"
curl -s -X POST "$BASE/v1/memories/serve/" -H "$B3O" -H "$J" -d '{
  "scope_app":"'"$SCOPE"'","query":"배포 창구 일정","request_id":"'"$RID"'","top_k":8}' \
| python3 -c "import sys,json; o=json.load(sys.stdin); assert o['reason']=='idempotent-replay'; print('  ✓ 멱등 재생')"

say "── 5. 영수증 3중 검증"
python3 - "$SERVE" <<'PYEOF'
import sys, json, os, urllib.request
receipt = json.loads(sys.argv[1])["receipt"]
key = open(os.path.expanduser("~/.forget/keys/b3o-desktop.key")).read().strip()
body = {"receipt": receipt, "expected": {"query": "배포 창구 일정",
        "grantee": "b3o-desktop", "scope_app": os.environ.get("SCOPE", receipt["scope_app"])}}
req = urllib.request.Request("http://localhost:8000/v1/receipts/verify/",
    data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
v = json.loads(urllib.request.urlopen(req).read())
assert v["valid"] and v["signature_valid"] and v["persistence_valid"] and v["binding_valid"]
print("  ✓ 서명·영속·결합 전부 유효")
PYEOF

say "── 6. 쓰기 게이트 (b3o.* 스코프는 human_approved 필수)"
NO=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/v1/memories/" -H "$B3O" -H "$J" -d '{
  "text":"사용자 선호: 다크 모드","app_id":"b3o.smoke-ws"}')
OK=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/v1/memories/" -H "$B3O" -H "$J" -d '{
  "text":"사용자 선호: 다크 모드","app_id":"b3o.smoke-ws","human_approved":true}')
[ "$NO" = "403" ] && [ "$OK" = "200" ] && say "  ✓ 없으면 403 · 명시 true면 200"

say "── 7. 회수"
curl -s -X POST "$BASE/v1/grants/$GID/revoke" -H "$OWNER" > /dev/null && say "  ✓ 회수됨"
say "═══ 상대역 전 구간 관통 성공 — 브로커가 붙는 순간 이 스크립트가 E2E의 절반"
