#!/usr/bin/env python3
"""릴레이 웹훅을 Paddle에 등록하고, 발급된 서명 시크릿을 stdout으로 내보낸다.

실행 (등록 + Fly 시크릿 주입까지 한 줄):
  python3 services/cloud-relay/register_webhook.py | ~/.fly/bin/flyctl secrets import -a forget-cloud-relay

stdout은 PADDLE_WEBHOOK_SECRET=... 한 줄뿐 (파이프 안전), 진행 로그는 stderr.
되돌리기: Paddle 대시보드 → Developer tools → Notifications에서 삭제.
"""

import json
import os
import sys
import urllib.request

ENDPOINT = "https://forget-cloud-relay.fly.dev/webhooks/paddle"
EVENTS = [
    "subscription.activated",
    "subscription.canceled",
    "subscription.past_due",
    "transaction.completed",
]

env = {}
for line in open(os.path.expanduser("~/Documents/Mem1/.secrets/paddle-payments.env")):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()

request = urllib.request.Request(
    "https://api.paddle.com/notification-settings",
    method="POST",
    data=json.dumps({
        "description": "forget cloud relay",
        "destination": ENDPOINT,
        "type": "url",
        "subscribed_events": EVENTS,
    }).encode(),
    headers={"Authorization": f"Bearer {env['PADDLE_API_KEY']}", "Content-Type": "application/json"},
)
with urllib.request.urlopen(request, timeout=20) as response:
    data = json.loads(response.read()).get("data") or {}

print(f"등록 완료: {data.get('id')} → {ENDPOINT}", file=sys.stderr)
print(f"구독 이벤트: {', '.join(EVENTS)}", file=sys.stderr)
print(f"PADDLE_WEBHOOK_SECRET={data.get('endpoint_secret_key')}")
