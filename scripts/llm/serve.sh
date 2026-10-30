#!/usr/bin/env bash
# GPU 서버(L4 24GB)에서 Qwen3.8-27B를 vLLM으로 띄웁니다. 먼저 setup-gpu.sh 를 한 번 실행하세요.
#   bash scripts/llm/serve.sh                              # 앞에서 실행
#   tmux new -d -s vllm 'bash scripts/llm/serve.sh'        # 뒤에서 실행 (tmux attach -t vllm 으로 보기)
#
# 127.0.0.1:8001 에만 열고 API 키를 요구합니다. 내 PC에서는 SSH 터널로 붙습니다:
#   ssh -N -L 8001:127.0.0.1:8001 <GPU 서버>
set -euo pipefail

VENV="${VLLM_VENV:-$HOME/venv-vllm}"
MODEL_REPO="${LLM_MODEL_REPO:-avyukth/Qwen3.8-27B-AWQ-INT4}"
MODEL_REV="${LLM_MODEL_REV:-5a2ee524cbc9f3ac5df12729ecf0c4b57f311192}"
SERVED_NAME="${LLM_MODEL:-qwen3.8-27b}"
PORT="${LLM_PORT:-8001}"
KEY_FILE="$HOME/.config/ymca/vllm-api-key"

# API 키는 명령줄 인자 대신 환경변수(VLLM_API_KEY)로 넘깁니다. 인자는 ps 로 같은 서버의 다른 사용자에게 보입니다
if [[ -z "${VLLM_API_KEY:-}" ]]; then
  if [[ ! -s "$KEY_FILE" ]]; then
    mkdir -p "$(dirname "$KEY_FILE")"
    (umask 077 && python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > "$KEY_FILE")
    echo "API 키를 새로 만들었습니다: $KEY_FILE"
    echo "내 PC .env 의 LLM_API_KEY 에 이 값을 넣으세요 (팀 공유는 채팅으로, 커밋 금지)"
  fi
  VLLM_API_KEY="$(cat "$KEY_FILE")"
  export VLLM_API_KEY
fi

# L4 메모리 배분: 가중치 약 17.7GiB + KV 캐시. 문맥 8K, 동시 8개(L4 처리량 포화 지점)
exec "$VENV/bin/vllm" serve "$MODEL_REPO" \
  --revision "$MODEL_REV" \
  --served-model-name "$SERVED_NAME" \
  --host 127.0.0.1 --port "$PORT" \
  --max-model-len 8192 \
  --max-num-seqs 8 \
  --gpu-memory-utilization 0.93 \
  --language-model-only \
  --reasoning-parser qwen3 \
  "$@"
