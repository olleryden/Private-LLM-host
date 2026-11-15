#!/usr/bin/env bash
# Opt-in private remote controls; does not start Qwen or WebUI.
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec /usr/bin/python3 "$repo_dir/control/remote.py" "$@"
