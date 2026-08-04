#!/usr/bin/env python3
"""forget cloud Pro 상품·가격을 라이브 Paddle에 생성 (1회용).

실행:  python3 services/cloud-relay/create_product.py
출력된 PADDLE_PRODUCT_ID / PADDLE_PRICE_ID_PRO 두 줄이 배선 재료.
되돌리기: Paddle 대시보드에서 상품 Archive.
"""

import json
import os
import urllib.request

env = {}
for line in open(os.path.expanduser("~/Documents/Mem1/.secrets/paddle-payments.env")):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()

KEY = env["PADDLE_API_KEY"]
BASE = "https://api.paddle.com"


def call(method: str, path: str, body: dict | None = None):
    request = urllib.request.Request(
        f"{BASE}{path}",
        method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read()).get("data")


product = call("POST", "/products", {
    "name": "forget cloud Pro",
    "description": (
        "Deep recall without heating your laptop — 2,000 deep recalls/month "
        "on the certified model. Memory itself never leaves your machine."
    ),
    "tax_category": "saas",
})
print(f"상품 생성: {product['id']}  ({product['name']}, {product['status']})")

price = call("POST", "/prices", {
    "product_id": product["id"],
    "description": "Pro monthly",
    "unit_price": {"amount": "800", "currency_code": "USD"},
    "billing_cycle": {"interval": "month", "frequency": 1},
    "quantity": {"minimum": 1, "maximum": 1},
})
print(f"가격 생성: {price['id']}  ($8.00 USD / month)")
print("\n→ 배선용 두 줄:")
print(f"PADDLE_PRODUCT_ID={product['id']}")
print(f"PADDLE_PRICE_ID_PRO={price['id']}")
