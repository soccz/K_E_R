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

echo "[publish] companies/ → HTML 렌더 → $SITE_KER_DIR"
.venv/bin/python -c "
from pathlib import Path
from pipeline.site_renderer import render_all
n_companies, n_reports = render_all(Path('companies'), Path('$SITE_KER_DIR'))
print(f'  rendered: {n_companies} companies, {n_reports} reports')
"

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
