#!/bin/bash
# K_E_R 일간 메모 자동 실행 wrapper.
# systemd timer가 매일 16:00 KST에 호출.
#
# 흐름:
#   1) daily_trigger 검사 (가격 ±5% / DART 공시 등 4종 임계치)
#   2) 트리거 통과 시 daily_note_builder가 LLM 호출 → daily_notes/<YYYY-MM-DD>.md
#   3) publish_site.sh로 사이트 렌더 + soccz.github.io push
#   4) 트리거 없으면 silently 종료 (페르소나 정직 — 억지 발행 X)
#
# 수동 실행: bin/run_daily.sh
# Dry-run (트리거 검사만): bin/run_daily.sh --check

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="$REPO_ROOT/.venv/bin/python"
LOG_TS=$(date '+%Y-%m-%d %H:%M:%S %Z')
TODAY=$(date '+%Y-%m-%d')

echo ""
echo "=========================================="
echo "[$LOG_TS] K_E_R daily run starting"
echo "=========================================="

# .env 로드
if [ -f "$REPO_ROOT/.env" ]; then
  set -a
  source "$REPO_ROOT/.env"
  set +a
fi

if [ -z "${DART_API_KEY:-}" ]; then
  echo "ERROR: DART_API_KEY 없음 — daily 실행 차단."
  exit 1
fi

DRY_RUN=0
if [ "${1:-}" = "--check" ]; then
  DRY_RUN=1
  echo "[daily] DRY-RUN — 트리거 검사만 실행"
fi

# 1) 트리거 검사
echo ""
echo "[daily] 1단계 — 임계치 검사"
TRIGGER_JSON="$REPO_ROOT/pipeline/cache/daily_trigger_${TODAY}.json"
mkdir -p "$REPO_ROOT/pipeline/cache"

set +e
"$PYTHON" -m pipeline.daily_trigger --check --save "$TRIGGER_JSON"
TRIGGER_RC=$?
set -e

if [ $TRIGGER_RC -ne 0 ]; then
  echo "[daily] 트리거 검사 실패 (rc=$TRIGGER_RC) — 종료"
  exit $TRIGGER_RC
fi

# 발행 여부 확인
SHOULD_PUBLISH=$("$PYTHON" -c "
import json
with open('$TRIGGER_JSON') as f:
    d = json.load(f)
print('1' if d.get('should_publish') else '0')
")

if [ "$SHOULD_PUBLISH" = "0" ]; then
  echo "[daily] 트리거 0건 — 일간 메모 미발행 (페르소나 정직 처리)"
  exit 0
fi

if [ $DRY_RUN -eq 1 ]; then
  echo "[daily] DRY-RUN 종료 — 트리거는 통과됐으나 LLM 호출·push는 skip"
  exit 0
fi

# 2) 일간 메모 LLM 생성
echo ""
echo "[daily] 2단계 — LLM 호출 + 마크다운 생성"

NOTE_PATH="$REPO_ROOT/daily_notes/${TODAY}.md"
mkdir -p "$REPO_ROOT/daily_notes"

"$PYTHON" - << EOF
from pathlib import Path
from pipeline.daily_trigger import evaluate_all_triggers
from pipeline.daily_note_builder import build_daily_note
from pipeline.watchlist_parser import parse_watchlist
from pipeline import config

watchlist = parse_watchlist(config.WATCHLIST_PATH.read_text(encoding='utf-8'))
report = evaluate_all_triggers(watchlist)

if not report.should_publish():
    print('[daily] 트리거 변동 — 0건 (재검사). 메모 건너뛰기.')
    raise SystemExit(0)

note = build_daily_note(report, watchlist, top_n=3)
if note is None:
    print('[daily] 메모 빌드 실패')
    raise SystemExit(2)

# LLM 실패 가드 — observation이 비었거나 '(LLM 호출 실패' 시 push 차단.
if not note.is_valid:
    print(f'[daily] LLM 호출 실패 또는 observation 비어있음 — push 차단')
    print(f'  observation 첫 200자: {note.observation[:200]}')
    raise SystemExit(3)

out = Path('$NOTE_PATH')
note.save(out)
print(f'[daily] saved: {out} ({len(note.to_markdown())} chars, {len(note.ticker_cards)} cards)')
EOF

PYTHON_RC=$?
if [ $PYTHON_RC -eq 3 ]; then
  echo "[daily] LLM 가드 트리거 — 사이트 push 없이 종료"
  exit 0
fi
if [ $PYTHON_RC -ne 0 ]; then
  echo "[daily] 메모 빌드 실패 (rc=$PYTHON_RC)"
  exit $PYTHON_RC
fi

if [ ! -f "$NOTE_PATH" ]; then
  echo "[daily] 메모 파일 없음 — push 차단"
  exit 2
fi

# 3) 사이트 렌더 + push
echo ""
echo "[daily] 3단계 — 사이트 렌더 + push"
bash "$REPO_ROOT/bin/publish_site.sh"

# 4) report repo도 commit (메모 누적 → 시계열 일지)
echo ""
echo "[daily] 4단계 — report repo commit"
cd "$REPO_ROOT"
git add daily_notes/
if ! git diff --cached --quiet; then
  git commit -m "daily: ${TODAY} 일간 메모 자동 발행

트리거 통과 → LLM 학술 톤 메모 생성·push.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>" 2>&1 | tail -2
  git push origin main 2>&1 | tail -2
else
  echo "[daily] commit 변경 없음"
fi

echo ""
echo "=========================================="
echo "[$LOG_TS] K_E_R daily run 완료"
echo "=========================================="
