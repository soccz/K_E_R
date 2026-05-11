#!/bin/bash
# 24/24 자동 채우기 batch — 모든 활성 PERIOD 끝까지.
# systemd transient unit으로 실행 (Claude Code/VSCode 독립).
#
# 사용:
#   systemd-run --user --unit=k_e_r-fill-batch \
#     --working-directory=/mnt/20t/report \
#     bash bin/run_fill_batch.sh

set -uo pipefail

# systemd 환경에서 PATH 보강
export PATH="$HOME/.local/bin:$HOME/.local/share/claude/versions:$PATH"

REPO_ROOT="/mnt/20t/report"
cd "$REPO_ROOT"

LOG_DIR="$REPO_ROOT/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/fill_batch_$(date +%Y%m%d_%H%M).log"

{
  echo "=========================================="
  echo "[fill-batch] 시작 $(date '+%Y-%m-%d %H:%M:%S')"
  echo "  TIMEOUT 30min/call (best-effort fallback 적용)"
  echo "  Hard limit 90min/종목"
  echo "  systemd transient unit — Claude Code/VSCode 독립"
  echo "=========================================="

  # .env 로드
  if [ -f "$REPO_ROOT/.env" ]; then
    set -a; source "$REPO_ROOT/.env"; set +a
  fi

  attempts=0
  max_attempts=30
  while [ $attempts -lt $max_attempts ]; do
    if PICK=$("$REPO_ROOT/.venv/bin/python" -m pipeline.period_picker --format csv 2>&1); then
      PERIOD=$(echo "$PICK" | cut -d, -f1)
      TICKER=$(echo "$PICK" | cut -d, -f4)
      attempts=$((attempts+1))
      echo ""
      echo ">>> [$attempts/$max_attempts] PERIOD=$PERIOD TICKER=$TICKER 시작 $(date '+%H:%M:%S')"
      # 매 ticker push: 사용자가 사이트에서 점진 완성 확인 가능 + batch timeout/crash 시 손실 X
      if CLAUDE_CODE_TIMEOUT_SEC=1800 GIT_AUTO_PUSH=1 SITE_AUTO_PUBLISH=1 \
         timeout 5400 bash "$REPO_ROOT/bin/run_weekly.sh" 2>&1; then
        echo ">>> [$attempts] OK $(date '+%H:%M:%S')"
      else
        rc=$?
        echo ">>> [$attempts] FAIL rc=$rc $(date '+%H:%M:%S')"
      fi
    else
      echo "[done] period_picker rc != 0 — 모든 활성 PERIOD 24/24 완료 또는 다음 마감일 대기"
      break
    fi
  done

  echo ""
  echo "=========================================="
  echo "[fill-batch] 처리 완료, push + publish $(date '+%H:%M:%S')"
  echo "=========================================="
  bash "$REPO_ROOT/bin/push_results.sh" 2>&1 || echo "(push 실패)"
  bash "$REPO_ROOT/bin/publish_site.sh" 2>&1 || echo "(publish 실패)"

  echo ""
  echo "[fill-batch] 종료 $(date '+%H:%M:%S')"
} > "$LOG" 2>&1
