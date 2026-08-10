#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "가상환경이 없습니다. README의 설치 절차를 먼저 실행하세요." >&2
  exit 1
fi

exec .venv/bin/python tui_main.py
