#!/bin/bash

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

if command -v caffeinate >/dev/null 2>&1; then
  caffeinate -u -t 2
  echo "화면 켜기를 요청했습니다."
  exit 0
fi

echo "caffeinate 명령을 찾을 수 없어 화면 켜기 요청을 보낼 수 없습니다." >&2
exit 1
