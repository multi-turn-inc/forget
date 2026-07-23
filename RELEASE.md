# Release — 두 커맨드로 베타 깔때기 개통

현재 상태 (2026-07-24): **PyPI에 forget-ai 미배포 (404)** — README 1행이 모든 사용자에게 실패.
**npm forget-connect는 0.1.0 (7/10, 훅 이전)** — 실사용자는 구버전 인스톨러를 받음.
아티팩트는 빌드·검사 완료 (`dist/`, twine PASSED · npm pack 11 files, assets 포함).

## 1. PyPI — forget-ai 0.2.0
```bash
cd <repo>
.venv/bin/python -m twine upload dist/*   # PyPI 계정/토큰 필요
```

## 2. npm — forget-connect 0.3.0
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
