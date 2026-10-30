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

# FlashInfer 샘플러는 처음 쓸 때 CUDA 커널을 컴파일하는데 서버에 nvcc·ninja 가 없습니다. PyTorch 샘플러를 씁니다
export VLLM_USE_FLASHINFER_SAMPLER=0

# L4 메모리 배분: 가중치 16.7GiB(비전 인코더 제외) + 나머지를 KV 캐시로. 문맥 12K, 동시 최대 8개
# 문맥 12K 는 backend/app/llm/prompts.py 의 입력 길이 예산과 짝입니다. 줄이면 그쪽 예산도 줄이세요
# prefix caching 은 하이브리드(Gated DeltaNet) 모델에서 실험 기능('align' 모드)이라 끕니다
exec "$VENV/bin/vllm" serve "$MODEL_REPO" \
  --revision "$MODEL_REV" \
  --served-model-name "$SERVED_NAME" \
  --host 127.0.0.1 --port "$PORT" \
  --max-model-len 12288 \
  --max-num-seqs 8 \
  --gpu-memory-utilization 0.95 \
  --language-model-only \
  --no-enable-prefix-caching \
  --reasoning-parser qwen3 \
  "$@"
