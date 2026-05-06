#!/bin/bash
# K_E_R 주말판 wrapper.
# 원래 의도: 산업노트 1편 (industry_note_generator.py).
# 현재: 산업노트 generator 미구현 → 종목 보고서 1편으로 대체 (워치리스트 회전).
# 결과: 주 2편 = 평일판 종목보고서 + 주말판 종목보고서.
# 산업노트 구현 후 이 파일을 진짜 산업노트 로직으로 교체.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_TS=$(date '+%Y-%m-%d %H:%M:%S %Z')

echo ""
echo "=========================================="
echo "[$LOG_TS] K_E_R weekend run (산업노트 미구현 — 종목 보고서로 대체)"
echo "=========================================="

exec "$REPO_ROOT/bin/run_weekly.sh"
