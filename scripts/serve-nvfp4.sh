#!/usr/bin/env bash
# Manual foreground launch. Does not install or enable any boot service.
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
context_length="${1:-32768}"
if [[ ! "$context_length" =~ ^[1-9][0-9]*$ ]] || (( $# > 1 )); then
  echo "Usage: bash scripts/serve-nvfp4.sh [context_tokens]" >&2
  exit 2
fi

export PATH="$repo_dir/.venv-nvfp4/bin:$PATH"
# FlashInfer may JIT with a toolkit found on PATH, independently of the
# CUDA runtime bundled with PyTorch. Make that toolkit's runtime visible.
cuda_toolkit_dir="${CUDA_HOME:-${CUDA_PATH:-}}"
if [[ -z "$cuda_toolkit_dir" ]] && command -v nvcc >/dev/null; then
  cuda_toolkit_dir="$(dirname -- "$(dirname -- "$(command -v nvcc)")")"
fi
if [[ -n "$cuda_toolkit_dir" ]]; then
  for runtime_dir in "$cuda_toolkit_dir/targets/x86_64-linux/lib" "$cuda_toolkit_dir/lib64"; do
    if compgen -G "$runtime_dir/libcudart.so.*" >/dev/null; then
      export LD_LIBRARY_PATH="$runtime_dir${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
      break
    fi
  done
fi
if [[ ! -x .venv-nvfp4/bin/vllm ]]; then
  echo "Missing vLLM environment. Follow SETUP_LOG.md first." >&2
  exit 1
fi
if ! command -v ninja >/dev/null; then
  echo "Ninja is missing from PATH. Follow SETUP_LOG.md section 8." >&2
  exit 1
fi
if [[ ! -s .secrets/vllm-api-key ]]; then
  echo "Missing API key. Follow SETUP_LOG.md section 6." >&2
  exit 1
fi
if [[ ! -f models/Qwen3.8-27B-NVFP4-NVIDIA/config.json ]]; then
  echo "Missing model configuration. Follow SETUP_LOG.md section 4." >&2
  exit 1
fi
VLLM_API_KEY="$(cat .secrets/vllm-api-key)"
export VLLM_API_KEY

exec .venv-nvfp4/bin/vllm serve models/Qwen3.8-27B-NVFP4-NVIDIA \
  --served-model-name qwen3.8-27b \
  --host 127.0.0.1 --port 8000 \
  --tensor-parallel-size 1 \
  --max-model-len "$context_length" \
  --max-num-seqs 1 \
  --max-num-batched-tokens 1024 \
  --gpu-memory-utilization 0.90 \
  --kv-cache-dtype fp8_e4m3 \
  --enforce-eager \
  --kernel-config '{"enable_flashinfer_autotune":false}' \
  --language-model-only \
  --reasoning-parser qwen3 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder
