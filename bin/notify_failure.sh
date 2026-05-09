#!/bin/bash
# K_E_R systemd OnFailure 핸들러 — ntfy.sh로 모바일 푸시.
#
# 사용:
#   bash bin/notify_failure.sh <failed-unit-name>
#
# 설정 (.env):
#   NTFY_TOPIC=ker-soccz-failures-<random>  # 모바일 ntfy 앱에서 같은 topic 구독
#   NTFY_SERVER=https://ntfy.sh             # 옵션 (default: ntfy.sh)
#
# NTFY_TOPIC 미설정 시 알림 skip (silent fail — 알림은 부수효과).

set -uo pipefail

UNIT="${1:-unknown}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# .env 로드
if [ -f "$REPO_ROOT/.env" ]; then
  set -a; source "$REPO_ROOT/.env"; set +a
fi

if [ -z "${NTFY_TOPIC:-}" ]; then
  exit 0  # silent — topic 없으면 알림 skip
fi

NTFY_SERVER="${NTFY_SERVER:-https://ntfy.sh}"

# 마지막 30줄 (로그 파일이 있으면)
LOG_FILE="$REPO_ROOT/logs/${UNIT//k_e_r-/}.log"
LOG_FILE="${LOG_FILE//.service/}"
TAIL_TXT=""
if [ -f "$LOG_FILE" ]; then
  TAIL_TXT=$(tail -n 30 "$LOG_FILE" 2>/dev/null | tr '\n' ' ' | head -c 1500)
fi

TS=$(date '+%Y-%m-%d %H:%M %Z')
TITLE="❌ K_E_R 실패: $UNIT"
BODY="시각: $TS

마지막 로그 30줄:
$TAIL_TXT"

curl -fsS \
  -H "Title: $TITLE" \
  -H "Priority: high" \
  -H "Tags: warning,robot" \
  -H "Click: https://github.com/soccz/K_E_R/actions" \
  -d "$BODY" \
  "$NTFY_SERVER/$NTFY_TOPIC" > /dev/null 2>&1 || true

exit 0
