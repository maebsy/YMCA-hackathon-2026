#!/usr/bin/env bash
# GPU 서버에 vLLM 실행 환경과 모델을 준비합니다. 한 번만 실행하면 됩니다.
#   bash scripts/llm/setup-gpu.sh
#
# 해커톤 서버 규칙에 맞춰 사용자 공간(~/venv-vllm, ~/.cache)만 씁니다. apt·드라이버·CUDA는 건드리지 않습니다.
set -euo pipefail

VLLM_VERSION="${VLLM_VERSION:-0.32.0}"
VENV="${VLLM_VENV:-$HOME/venv-vllm}"
MODEL_REPO="${LLM_MODEL_REPO:-avyukth/Qwen3.8-27B-AWQ-INT4}"
MODEL_REV="${LLM_MODEL_REV:-5a2ee524cbc9f3ac5df12729ecf0c4b57f311192}"
export PATH="$HOME/.local/bin:$PATH"

echo "== GPU·드라이버·디스크"
nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used --format=csv,noheader
df -h "$HOME" | tail -1

if ! command -v uv >/dev/null; then
  echo "== uv 설치 (~/.local/bin)"
  curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
fi

# Triton이 실행 중에 C 확장을 컴파일해서 Python.h 가 필요합니다. 서버 python3 에는 개발 헤더가 없고 apt는 쓰지 않으므로
# 헤더가 들어 있는 uv 관리 파이썬을 씁니다
has_headers() {
  "$VENV/bin/python" -c 'import os, sysconfig, sys; sys.exit(not os.path.exists(os.path.join(sysconfig.get_paths()["include"], "Python.h")))'
}
if [[ -x "$VENV/bin/python" ]] && ! has_headers; then
  echo "== $VENV 에 Python.h 가 없어 다시 만듭니다"
  rm -rf "$VENV"
fi
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "== $VENV 만들기 (uv 관리 Python 3.12)"
  uv venv "$VENV" --python 3.12 --managed-python --seed
fi

echo "== vLLM $VLLM_VERSION 설치 (드라이버에 맞는 PyTorch 자동 선택)"
uv pip install --python "$VENV/bin/python" "vllm==$VLLM_VERSION" --torch-backend=auto
"$VENV/bin/python" - <<'EOF'
import torch, vllm
print("vllm", vllm.__version__, "| torch", torch.__version__, "| CUDA", torch.version.cuda,
      "| GPU", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "사용 불가")
EOF

echo "== 모델 내려받기: $MODEL_REPO @ ${MODEL_REV:0:12} (약 18GB)"
"$VENV/bin/hf" download "$MODEL_REPO" --revision "$MODEL_REV"
echo "✅ 준비 완료. 실행: bash scripts/llm/serve.sh"
