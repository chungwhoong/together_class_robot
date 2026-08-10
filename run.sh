#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "가상환경이 없습니다. README의 설치 절차를 먼저 실행하세요." >&2
  exit 1
fi

if ! systemctl is-active --quiet dahamkke-touchscreen.service 2>/dev/null; then
  echo "터치스크린 GUI 서비스를 시작합니다." >&2
  sudo systemctl start dahamkke-touchscreen.service
fi

for _ in {1..50}; do
  [[ -S /tmp/dahamkke-bot-control.sock ]] && break
  sleep 0.1
done

if [[ ! -S /tmp/dahamkke-bot-control.sock ]]; then
  echo "GUI 공유 제어 소켓을 찾을 수 없습니다." >&2
  exit 1
fi

exec .venv/bin/python controller_main.py
