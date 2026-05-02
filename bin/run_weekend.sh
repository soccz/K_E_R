#!/bin/bash
# K_E_R 주말판 실행 wrapper (산업노트).
# systemd timer가 호출 (또는 수동: bin/run_weekend.sh)
#
# TODO: industry_note_generator.py 구현 후 활성화.
# 현재는 stub.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LOG_TS=$(date '+%Y-%m-%d %H:%M:%S %Z')
echo ""
echo "=========================================="
echo "[$LOG_TS] K_E_R weekend run (stub — 산업노트 미구현)"
echo "=========================================="
echo "skipping. 산업노트 generator 구현 후 활성화."
exit 0
