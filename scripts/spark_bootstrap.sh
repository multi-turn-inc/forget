#!/usr/bin/env bash
# DGX Spark(edgexpert-1086, GB10 121GB) — 기억 하네스 중간 루프용 로컬 모델 서버 준비 (2026-09-07).
# 실행은 정훈 손. 모델 가중치 다운로드가 포함되므로 허락 뒤에 돌린다.
#   ssh home-nvidia 'bash -s' < scripts/spark_bootstrap.sh            # 점검만 (기본)
#   ssh home-nvidia 'bash -s' < scripts/spark_bootstrap.sh -- serve   # 서버 기동
# 맥 쪽 터널:  ssh -N -L 18813:127.0.0.1:18813 home-nvidia   → FORGET_MID_URL=http://127.0.0.1:18813/v1
set -u
MODE="${2:-check}"
MODEL_REPO="${SPARK_MODEL_REPO:-Qwen/Qwen3.5-32B-GGUF}"      # 121GB 통합 메모리: 32B Q8이 편하게 들어간다. 9B는 속도용 대안.
MODEL_FILE="${SPARK_MODEL_FILE:-Qwen3.5-32B-Q8_0.gguf}"
PORT="${SPARK_PORT:-18813}"
echo "== host: $(hostname)  uptime: $(uptime | sed 's/.*load/load/')"
nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader 2>/dev/null || echo "nvidia-smi 없음"
echo "== 돌고 있는 추론 서버"; pgrep -af "llama-server|ollama|vllm|sglang" | grep -v pgrep || echo "(없음)"
echo "== 도구"; for t in llama-server ollama docker python3; do printf "  %-12s %s\n" "$t" "$(command -v $t || echo -)"; done
echo "== 디스크"; df -h / | tail -1
echo "== 모델 파일"; ls -la ~/models/*.gguf 2>/dev/null || echo "(~/models 비어 있음)"
[ "$MODE" = "check" ] && { echo "== 점검만 했다. serve 모드는 '-- serve'."; exit 0; }
mkdir -p ~/models
if [ ! -f ~/models/"$MODEL_FILE" ]; then
  echo "== 모델 받기: $MODEL_REPO/$MODEL_FILE (정훈 허락 전제)"
  python3 -m pip install -q -U huggingface_hub >/dev/null 2>&1
  python3 -c "from huggingface_hub import hf_hub_download; hf_hub_download('$MODEL_REPO','$MODEL_FILE',local_dir='$HOME/models')" || { echo "다운로드 실패"; exit 1; }
fi
if ! command -v llama-server >/dev/null; then
  echo "== llama.cpp 없음 — ollama가 있으면 그것으로, 없으면 llama.cpp 빌드 필요(cmake -DGGML_CUDA=ON)"; command -v ollama >/dev/null && { ollama serve >/tmp/ollama.log 2>&1 & sleep 3; echo "ollama :11434"; exit 0; }; exit 1
fi
nohup llama-server -m ~/models/"$MODEL_FILE" --host 127.0.0.1 --port "$PORT" -c 32768 -ngl 999 --parallel 2 --jinja >/tmp/llama-server.log 2>&1 &
sleep 8; curl -s "http://127.0.0.1:$PORT/v1/models" | head -c 200; echo; echo "== 서버 :$PORT (로그 /tmp/llama-server.log)"
