#!/bin/bash
# K_E_R 평일판 실행 wrapper.
# systemd timer가 호출 (또는 수동: bin/run_weekly.sh)
#
# 현재는 placeholder — 삼성전자 사업보고서 1편.
# TODO: 워치리스트 24종목 + DART 신규 공시 검색 → 그 주 가장 임팩트 큰 종목 자동 선정.

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

# 기본 타깃: 삼성전자 직전 사업보고서
# TODO: 자동 선정 로직 (orchestrator)
TICKER="${WEEKDAY_TICKER:-005930}"
BSNS_YEAR="${WEEKDAY_BSNS_YEAR:-2025}"
REPRT_CODE="${WEEKDAY_REPRT_CODE:-11011}"
PERIOD="${WEEKDAY_PERIOD:-2025-annual}"

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
