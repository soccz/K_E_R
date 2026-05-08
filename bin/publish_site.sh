#!/bin/bash
# K_E_R 보고서 → soccz.github.io/projects/k-e-r/ 시각화 → push.
#
# 호출 시점: K_E_R run 완료 직후 (run_weekly.sh 마지막 단계)
# 또는 수동: bin/publish_site.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SITE_ROOT="/home/soccz/22tb/soccz.github.io"
SITE_KER_DIR="$SITE_ROOT/projects/k-e-r"

cd "$REPO_ROOT"

if [ ! -d "$SITE_ROOT" ]; then
  echo "[publish] $SITE_ROOT 없음 — skip"
  exit 0
fi

if [ ! -x .venv/bin/python ]; then
  echo "[publish] .venv 없음 — skip"
  exit 0
fi

# 워치리스트 24종목 ticker_market 캐시 일괄 갱신 (KRX rate limit 보호 ~3초).
# 실패해도 사이트 빌드는 진행 (캐시 stale 허용).
echo "[publish] ticker_market 캐시 24종목 일괄 갱신"
.venv/bin/python -m pipeline.bulk_ticker_refresh 2>&1 | tail -3 || \
  echo "  [warn] bulk fetch 일부 실패 — stale 캐시로 사이트 빌드"

echo ""
echo "[publish] companies/ + daily_notes/ → HTML 렌더 → $SITE_KER_DIR"
if ! .venv/bin/python -c "
from pathlib import Path
from pipeline.site_renderer import render_all
daily_dir = Path('daily_notes')
n_companies, n_reports, n_rendered = render_all(
    Path('companies'),
    Path('$SITE_KER_DIR'),
    watchlist_path=Path('_watchlist.md'),
    incremental=True,
    daily_notes_dir=daily_dir if daily_dir.exists() else None,
)
print(f'  발견: {n_companies} companies, {n_reports} reports')
print(f'  렌더: {n_rendered} (incremental — 변경된 것만)')
print(f'  일간 메모 디렉토리: {\"있음\" if daily_dir.exists() else \"없음 (Phase E 후 활성)\"}')
print(f'  마스터 인덱스: 워치리스트 24종목 + placeholder')
" 2>&1; then
  echo "[publish] 렌더 실패 — push 차단"
  exit 1
fi

# soccz.github.io repo commit + push
cd "$SITE_ROOT"

# git repo 아닌 경우 skip
if ! git rev-parse --is-inside-work-tree &>/dev/null; then
  echo "[publish] $SITE_ROOT 가 git repo 아님 — skip"
  exit 0
fi

git add projects/k-e-r/

if git diff --cached --quiet; then
  echo "[publish] 사이트 변경 없음 — skip commit"
  exit 0
fi

TS=$(date '+%Y-%m-%d %H:%M %Z')
git commit -m "k_e_r: report site update $TS

Auto-generated from K_E_R MD updates."

if git push origin main 2>&1; then
  echo "[publish] soccz.github.io push 성공 — Pages 자동 deploy 시작"
else
  echo "[publish] push 실패 — 다음 시도 때 재시도"
  exit 0
fi
