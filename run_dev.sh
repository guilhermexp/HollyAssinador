#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo "Prepare as dependências com ./build_macos.sh." >&2
  exit 1
fi
exec .venv/bin/python app.py "$@"
