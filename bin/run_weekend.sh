#!/bin/bash
# K_E_R 주말판 wrapper — 산업노트 generator (frame.md §6).
# 매주 일 21:00 KST k_e_r-weekend.timer가 호출.
#
# 흐름:
#   1) pick_sector — 워치리스트 13섹터 중 가장 오래 안 다룬 + DART 활동 큰 섹터 1개
#   2) build_industry_note — LLM 호출 → industry_notes/<YYYY-WNN>-<섹터>.md
#   3) publish_site → soccz.github.io/projects/k-e-r/ push
#
# 트리거 0건 (모든 섹터 단일 종목 등) 시 폴백: 평일판 (run_weekly.sh).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="$REPO_ROOT/.venv/bin/python"
LOG_TS=$(date '+%Y-%m-%d %H:%M:%S %Z')

echo ""
echo "=========================================="
echo "[$LOG_TS] K_E_R weekend run — 산업노트"
echo "=========================================="

if [ -f "$REPO_ROOT/.env" ]; then
  set -a; source "$REPO_ROOT/.env"; set +a
fi

if [ -z "${DART_API_KEY:-}" ]; then
  echo "ERROR: DART_API_KEY 없음 — weekend 차단"
  exit 1
fi

mkdir -p "$REPO_ROOT/industry_notes"

# 1) 산업노트 빌드
"$PYTHON" - << 'EOF'
from pathlib import Path
from pipeline.industry_note_builder import pick_sector, build_industry_note
from pipeline.watchlist_parser import parse_watchlist
from pipeline import config

watchlist = parse_watchlist(config.WATCHLIST_PATH.read_text(encoding='utf-8'))
industry_dir = Path('industry_notes')

pick = pick_sector(watchlist, industry_dir)
if pick is None:
    print('[weekend] 섹터 선정 실패 (페어 비교 가능 섹터 없음) — fallback to weekly')
    raise SystemExit(99)

print(f"[weekend] 선정 섹터: {pick.sector} ({len(pick.tickers)}종목, "
      f"마지막 {pick.last_covered_iso_week or 'never'}, 점수 {pick.score:.1f})")

note = build_industry_note(pick, cache_dir=Path('pipeline/cache'))
if note is None or not note.is_valid:
    print('[weekend] 산업노트 LLM 호출 실패 — push 차단')
    raise SystemExit(3)

out = industry_dir / f"{note.iso_week}-{note.sector}.md"
note.save(out)
print(f'[weekend] saved: {out} ({len(note.to_markdown())} chars, '
      f'비교 {len(note.ticker_comparison_table)}종목)')
EOF

PY_RC=$?
if [ $PY_RC -eq 99 ]; then
  echo "[weekend] 폴백 → run_weekly.sh"
  exec "$REPO_ROOT/bin/run_weekly.sh"
fi
if [ $PY_RC -eq 3 ]; then
  echo "[weekend] LLM 가드 차단 — push skip"
  exit 0
fi
if [ $PY_RC -ne 0 ]; then
  echo "[weekend] 빌드 실패 (rc=$PY_RC)"
  exit $PY_RC
fi

# 2) site 렌더 + push
bash "$REPO_ROOT/bin/publish_site.sh"

# 3) report repo commit
cd "$REPO_ROOT"
git add industry_notes/
if ! git diff --cached --quiet; then
  TS=$(date '+%Y-%m-%d %H:%M %Z')
  git commit -m "weekend: 산업노트 자동 발행 ${TS}

frame.md §6 주말판 — 워치리스트 섹터 페어 비교.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>" 2>&1 | tail -2
  git push origin main 2>&1 | tail -2
fi

echo ""
echo "=========================================="
echo "[$LOG_TS] K_E_R weekend run 완료"
echo "=========================================="
