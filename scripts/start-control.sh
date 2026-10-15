#!/usr/bin/env bash
# Starts/reopens one local control app. Does not start hosting or enable boot startup.
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec /usr/bin/python3 "$repo_dir/control/launcher.py" "$@"
