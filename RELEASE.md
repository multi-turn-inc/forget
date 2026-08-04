# Release — 두 커맨드로 베타 깔때기 개통

현재 상태 (2026-08-04): **0.4.0·0.5.2 출시 준비** — 다이얼 릴리스 (recall 다이얼 4기어·엔진 축 auto|local|byo|cloud·forget cloud 클라이언트·/forget 슬래시 커맨드 동봉·성능 캐시 1165→171ms). 직전 라이브: PyPI **0.3.9**·npm **0.5.1** (업데이트 인지 릴리스).

## 0. 출시 전 게이트 — 깔때기 리허설 (2분, 자동)
```bash
bash scripts/rehearse-funnel.sh   # 마지막 줄이 "funnel rehearsal: ALL GREEN"이어야 출시
```
빌드된 아티팩트 그대로, 격리 샌드박스(HOME+CODEX_HOME)에서 베타 사용자의 동선을 밟는다:
wheel 설치 → 서버 기동 → MCP add/search → tarball connect → 맨손 doctor → disconnect 잔존물 0.

## 1. PyPI — forget-ai 0.4.0
```bash
cd <repo>
.venv/bin/python -m twine upload dist/*   # PyPI 계정/토큰 필요
```

## 2. npm — forget-connect 0.5.2
```bash
cd packages/forget-connect
npm publish                                # npm 로그인 필요
```

## 출시 후 스모크 (5분)
```bash
pip install 'forget-ai[server]' && forget-server install-service && forget-server status
npx forget-connect@latest --dry-run
npx forget-connect@latest doctor
```

체크: forget.sh 프로덕션 반영(`site/ && vercel deploy --prod`)과 함께 나가면 사이트 커맨드가 실제로 동작.
