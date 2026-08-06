# 침묵 폴백 감사 (body A3, 2026-08-06)

`except Exception:`(무변수) 전수 목록. 판정: OBSERVABLE(폴백 결과가
표식을 남김) / FAIL-OPEN-OK(훅류 — 실패=침묵이 설계) / **MUTE(무흔적 — 수리 대상)**

- `forget/cli.py:309` — 확인 필요 · 직전: `return version("forget-ai")`
- `forget/cli.py:336` — MUTE? · 직전: `return str(_json.load(response)["info"]["version"])`
- `forget/cli.py:393` — 확인 필요 · 직전: `mcp_ok = bool(body.get("result", {}).get("tools"))`
- `forget/cli.py:450` — MUTE? · 직전: `False))`
- `forget/cli.py:487` — OBSERVABLE(log) · 직전: `probe_ok = "probe" in _json.dumps(found.get("result", {}))`
- `forget/cli.py:637` — 확인 필요 · 직전: `vec = embed_text(str(text or ""))`
- `forget/cli.py:741` — 확인 필요 · 직전: `raise`
- `forget/cli.py:872` — MUTE? · 직전: `return int(f.readline().split()[1]) // (1 << 20)`
- `forget/consolidation.py:138` — 확인 필요 · 직전: `return verdicts`
- `forget/consolidation.py:186` — 확인 필요 · 직전: `pairs = (stale_candidate_pairs(payload, project_id=project_id) or {}).`
- `forget/consolidation.py:220` — 확인 필요 · 직전: `supersedes_left -= 1`
- `forget/db.py:72` — 확인 필요 · 직전: `conn.commit()`
- `forget/mcp.py:65` — 확인 필요 · 직전: `username = getpass.getuser().strip()`
- `forget/mcp.py:1169` — OBSERVABLE(log) · 직전: `record_usage(current_project_id(), f"mcp.{name}", metadata={"surface":`
- `forget/providers.py:230` — MUTE? · 직전: `return _provider_counted(accounting, messages, facts)`
- `forget/providers.py:239` — MUTE? · 직전: `return _provider_counted(accounting, messages, facts)`
- `forget/providers.py:248` — MUTE? · 직전: `return _provider_counted(accounting, messages, facts)`
- `forget/providers.py:257` — MUTE? · 직전: `return _provider_counted(accounting, messages, facts)`
- `forget/providers.py:266` — MUTE? · 직전: `return _provider_counted(accounting, messages, facts)`
- `forget/providers.py:1176` — MUTE? · 직전: `return _rerank_with_cohere(query, memories, settings, top_n=top_n)`
- `forget/providers.py:1181` — MUTE? · 직전: `return _rerank_with_llm(query, memories, settings, top_n=top_n)`
- `forget/providers.py:1186` — MUTE? · 직전: `return _rerank_with_sentence_transformer(query, memories, settings, to`
- `forget/providers.py:1191` — MUTE? · 직전: `return _rerank_with_huggingface(query, memories, settings, top_n=top_n`
- `forget/providers.py:1196` — MUTE? · 직전: `return _rerank_with_zero_entropy(query, memories, settings, top_n=top_`
- `forget/scope_guard.py:45` — 확인 필요 · 직전: `username = getpass.getuser().strip()`
- `forget/store.py:68` — MUTE? · 직전: `return str(__version__)`
- `forget/store.py:4519` — MUTE? · 직전: `}`
- `forget/store.py:4541` — MUTE? · 직전: `return int(value)`
- `forget/store.py:4700` — 확인 필요 · 직전: `indices = [i for i in parsed if isinstance(i, int) and 0 <= i < len(ca`
- `forget/store.py:8343` — MUTE? · 직전: `return os.getcwd(), "server_cwd"`
- `forget/store.py:9666` — MUTE? · 직전: `listing = get_task_state({"limit": 12}, project_id=project_id)`
- `forget/store.py:9708` — MUTE? · 직전: `]`
- `forget/store.py:9743` — MUTE? · 직전: `listing = get_task_state({"limit": 12}, project_id=project_id)`
- `forget/store.py:9779` — MUTE? · 직전: `listing = get_task_state({"limit": 8}, project_id=project_id)`
- `forget/store.py:11755` — 확인 필요 · 직전: `break`
- `forget/store.py:16761` — 확인 필요 · 직전: `cuda_device_name = str(torch.cuda.get_device_name(0))`
- `forget/updatecheck.py:44` — MUTE? · 직전: `return str(data.get("latest") or "")`
- `forget/updatecheck.py:58` — MUTE? · 직전: `return str(data.get("latest") or "")`
- `forget/updatecheck.py:63` — MUTE? · 직전: `latest = str(json.load(response)["info"]["version"])`
- `forget/updatecheck.py:68` — MUTE? · 직전: `cache.write_text(json.dumps({"latest": latest, "checked_at": time.time`

총계: MUTE 후보 25건 — P1에서 항목별 삼진(로그/표식/의도적 침묵 문서화)