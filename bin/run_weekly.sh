#!/bin/bash
# K_E_R 평일판 실행 wrapper.
# systemd timer가 호출 (또는 수동: bin/run_weekly.sh)
#
# 자동 PERIOD 전환:
#   - period_picker.py가 마감일 경과 + 24/24 미완성인 가장 오래된 PERIOD 선정
#   - 2025-annual 24/24 완료 → 5/15 후 자동 2026-q1 전환
#   - 모든 PERIOD 완료 시 exit 0 (다음 마감일까지 대기)
#
# Override (수동 디버그):
#   WEEKDAY_TICKER=005930 WEEKDAY_PERIOD=2025-annual bin/run_weekly.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="$REPO_ROOT/.venv/bin/python"
LOG_TS=$(date '+%Y-%m-%d %H:%M:%S %Z')

echo ""
echo "=========================================="
echo "[$LOG_TS] K_E_R weekday run starting"
echo "=========================================="

# .env 로드 (systemd EnvironmentFile이 처리하지만 수동 호출 대비)
if [ -f "$REPO_ROOT/.env" ]; then
  set -a
  source "$REPO_ROOT/.env"
  set +a
fi

if [ -z "${DART_API_KEY:-}" ]; then
  echo "ERROR: DART_API_KEY 없음. .env 또는 환경변수 확인."
  exit 1
fi

# 자동 PERIOD 전환 — period_picker.py가 활성 PERIOD + 다음 ticker 결정.
# Override 시: WEEKDAY_TICKER + WEEKDAY_PERIOD + WEEKDAY_BSNS_YEAR + WEEKDAY_REPRT_CODE
if [ -z "${WEEKDAY_TICKER:-}" ]; then
  if PICK=$("$PYTHON" -m pipeline.period_picker --format csv); then
    PERIOD=$(echo "$PICK" | cut -d, -f1)
    BSNS_YEAR=$(echo "$PICK" | cut -d, -f2)
    REPRT_CODE=$(echo "$PICK" | cut -d, -f3)
    TICKER=$(echo "$PICK" | cut -d, -f4)
  else
    PICK_RC=$?
    if [ "$PICK_RC" -eq 2 ]; then
      echo "[$LOG_TS] all-done: 모든 활성 PERIOD 24/24 완료 또는 다음 마감일 대기 — skip"
      exit 0
    fi
    echo "ERROR: PERIOD 선정 실패 (rc=$PICK_RC)"
    exit "$PICK_RC"
  fi
else
  TICKER="$WEEKDAY_TICKER"
  BSNS_YEAR="${WEEKDAY_BSNS_YEAR:-2025}"
  REPRT_CODE="${WEEKDAY_REPRT_CODE:-11011}"
  PERIOD="${WEEKDAY_PERIOD:-2025-annual}"
fi

echo "ticker=$TICKER bsns_year=$BSNS_YEAR reprt_code=$REPRT_CODE period=$PERIOD"

"$PYTHON" -m pipeline.run_dart generate \
  --ticker "$TICKER" \
  --bsns-year "$BSNS_YEAR" \
  --reprt-code "$REPRT_CODE" \
  --period "$PERIOD"

# GitHub auto-push — 기본 ON. 끄려면 GIT_AUTO_PUSH=0 환경변수.
if [ "${GIT_AUTO_PUSH:-1}" = "1" ]; then
  "$REPO_ROOT/bin/push_results.sh" || echo "(K_E_R push 실패 — 다음 실행 시 재시도)"
else
  echo "[git] K_E_R auto-push 비활성 (GIT_AUTO_PUSH=0)"
fi

# 시각화 사이트 publish — 기본 ON. 끄려면 SITE_AUTO_PUBLISH=0.
if [ "${SITE_AUTO_PUBLISH:-1}" = "1" ]; then
  "$REPO_ROOT/bin/publish_site.sh" || echo "(site publish 실패 — 다음 실행 시 재시도)"
else
  echo "[site] auto-publish 비활성 (SITE_AUTO_PUBLISH=0)"
fi

echo "[$LOG_TS] K_E_R weekday run done"
