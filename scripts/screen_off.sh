#!/bin/bash

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

if ! command -v pmset >/dev/null 2>&1; then
  echo "pmset 명령을 찾을 수 없습니다." >&2
  exit 1
fi

pmset displaysleepnow
echo "화면 끄기를 요청했습니다."
