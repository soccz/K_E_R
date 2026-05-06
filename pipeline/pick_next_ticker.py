"""다음으로 생성할 티커 선정 — 회전 오케스트레이터.

워치리스트 24종목을 순회하며 `companies/<name>/<period>/00_종합진단.md`가
없는 첫 종목 출력. 모두 완료된 경우 비-제로 종료(wrap 시점은 운영자가 결정).

Usage:
  python -m pipeline.pick_next_ticker --period 2025-annual
  → stdout: 000660
"""
from __future__ import annotations

import argparse
import sys

from pipeline import config
from pipeline.report_quality import is_usable_report
from pipeline.watchlist_parser import parse_watchlist


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", required=True, help="예: 2025-annual")
    args = parser.parse_args()

    watchlist_text = config.WATCHLIST_PATH.read_text(encoding="utf-8")
    entries = parse_watchlist(watchlist_text)

    for entry in entries:
        final_report = (
            config.COMPANIES_DIR / entry.name / args.period / "00_종합진단.md"
        )
        if not is_usable_report(final_report):
            print(entry.ticker)
            return 0

    print(f"all-done: 24종목 모두 {args.period} 완료", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
