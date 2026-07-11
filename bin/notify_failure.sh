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

# 텔레그램 폴백 (2026-07-12 수리): NTFY_TOPIC 미설정으로 4주간 실패 무통지였던 사고 재발 방지.
# .env의 TELEGRAM_* 우선, 없으면 prelude .env 크리덴셜 재사용 (읽기만).
if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] && [ -f /home/soccz/22tb/prelude/.env ]; then
  TELEGRAM_BOT_TOKEN=$(grep -E '^TELEGRAM_BOT_TOKEN=' /home/soccz/22tb/prelude/.env | head -1 | cut -d= -f2-)
  TELEGRAM_CHAT_ID=$(grep -E '^TELEGRAM_CHAT_ID=' /home/soccz/22tb/prelude/.env | head -1 | cut -d= -f2-)
fi

if [ -z "${NTFY_TOPIC:-}" ] && [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then
  exit 0  # 알림 경로가 정말 하나도 없을 때만 skip
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

if [ -n "${NTFY_TOPIC:-}" ]; then
  curl -fsS \
    -H "Title: $TITLE" \
    -H "Priority: high" \
    -H "Tags: warning,robot" \
    -H "Click: https://github.com/soccz/K_E_R/actions" \
    -d "$BODY" \
    "$NTFY_SERVER/$NTFY_TOPIC" > /dev/null 2>&1 || true
fi

if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
  curl -fsS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
    --data-urlencode "text=${TITLE}
${BODY}" > /dev/null 2>&1 || true
fi

exit 0
