#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f web/dist/index.html ]]; then
  echo '화면 빌드가 없습니다. npm ci && npm run build를 먼저 실행해 주세요.' >&2
  exit 1
fi
exec .venv/bin/python -m uvicorn backend.asgi:app --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log
