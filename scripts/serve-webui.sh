#!/usr/bin/env bash
# Manual chat UI startup; model and Tailscale Serve have separate lifecycles.
set -euo pipefail
umask 077
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

if [[ ! -x .venv-webui/bin/open-webui ]]; then
  echo "Open WebUI is not installed. Follow PHONE_CHAT.md." >&2
  exit 1
fi
if [[ ! -s .secrets/vllm-api-key ]]; then
  echo "Missing local model API key. Follow SETUP_LOG.md section 6." >&2
  exit 1
fi

.venv-webui/bin/python - <<'PY'
from pathlib import Path
import secrets

directory = Path('.secrets')
directory.mkdir(mode=0o700, exist_ok=True)
key = directory / 'webui-secret-key'
if not key.exists():
    with key.open('x') as stream:
        stream.write(secrets.token_urlsafe(48) + '\n')
key.chmod(0o600)
Path('.data/open-webui').mkdir(mode=0o700, parents=True, exist_ok=True)
PY

export PATH="$repo_dir/.venv-webui/bin:$PATH"
export DATA_DIR="$repo_dir/.data/open-webui"
export WEBUI_SECRET_KEY="$(cat .secrets/webui-secret-key)"
export OPENAI_API_BASE_URLS="http://127.0.0.1:8000/v1"
export OPENAI_API_KEYS="$(cat .secrets/vllm-api-key)"
export WEBUI_AUTH=true
export ENABLE_LOGIN_FORM=true
export ENABLE_SIGNUP=false
export ENABLE_OPENAI_API=true
export ENABLE_OLLAMA_API=false
export DEFAULT_MODELS=qwen3.8-27b
export UVICORN_WORKERS=1
export CUDA_VISIBLE_DEVICES=""
export USE_CUDA_DOCKER=false
# Chat only for this milestone; no embedding/voice downloads or tool execution.
export OFFLINE_MODE=true
export ENABLE_WEB_SEARCH=false
export ENABLE_CODE_EXECUTION=false
export ENABLE_CODE_INTERPRETER=false
export ENABLE_MEMORIES=false
export WEBUI_URL="${PLLM_WEBUI_URL:-http://127.0.0.1:8080}"
export CORS_ALLOW_ORIGIN="http://127.0.0.1:8080;http://localhost:8080;$WEBUI_URL"

exec .venv-webui/bin/open-webui serve --host 127.0.0.1 --port 8080
