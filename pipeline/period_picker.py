"""현재 시점에서 발행해야 할 PERIOD 자동 결정.

DART 정기공시 마감일(KIFRS 의무공시 시한) 기반으로 활성 PERIOD 결정:
  - 사업보고서(annual): 사업연도 종료 + 90일 (12/31 마감 → 다음해 3/31)
  - 반기보고서(half):   2분기 종료 + 45일 (6/30 마감 → 8/14)
  - 분기보고서(quarter): 분기 종료 + 45일 (3/31 → 5/15, 9/30 → 11/14)

규칙:
  1. 마감일 지난 PERIOD 중 워치리스트 24종목 미완성인 가장 오래된 것 = 활성
  2. 마감일 미경과 PERIOD는 데이터 불완전 → skip
  3. 모든 PERIOD 24/24 완성 → 다음 마감일까지 대기 (exit 2)

Usage:
  python -m pipeline.period_picker
  → stdout: "2025-annual,2025,11011,005930"  (period,year,reprt_code,next_ticker)
  exit 2: 모든 활성 PERIOD 완료 — 다음 마감일까지 대기
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pipeline import config
from pipeline.report_quality import is_usable_report
from pipeline.watchlist_parser import parse_watchlist


@dataclass(frozen=True)
class PeriodSpec:
    """DART 보고서 종류 정의."""

    period_label: str  # 예: "2025-annual", "2026-q1"
    bsns_year: int  # 사업연도
    reprt_code: str  # DART reprt_code
    filing_deadline: str  # YYYY-MM-DD — 의무공시 마감 (이 날짜 +1일부터 활성)


# 활성 후보 — 오래된 PERIOD부터 (가장 오래된 미완성이 우선).
# 새 PERIOD 추가 시 마감일 순으로 append.
_PERIODS: list[PeriodSpec] = [
    PeriodSpec("2025-annual", 2025, "11011", "2026-03-31"),
    PeriodSpec("2026-q1",     2026, "11013", "2026-05-15"),
    PeriodSpec("2026-h1",     2026, "11012", "2026-08-14"),
    PeriodSpec("2026-q3",     2026, "11014", "2026-11-14"),
    PeriodSpec("2026-annual", 2026, "11011", "2027-03-31"),
    PeriodSpec("2027-q1",     2027, "11013", "2027-05-15"),
]


def _is_deadline_passed(spec: PeriodSpec, today: datetime | None = None) -> bool:
    today = today or datetime.now()
    deadline = datetime.strptime(spec.filing_deadline, "%Y-%m-%d")
    return today >= deadline


def _next_unfinished_ticker(spec: PeriodSpec, watchlist) -> str | None:
    """24종목 중 현재 PERIOD 미완성 첫 ticker."""
    for entry in watchlist:
        final = config.COMPANIES_DIR / entry.name / spec.period_label / "00_종합진단.md"
        if not is_usable_report(final):
            return entry.ticker
    return None


def pick_active_period(today: datetime | None = None) -> tuple[PeriodSpec, str] | None:
    """가장 오래된 PERIOD 중 24/24 미완성 + 마감일 경과한 것 선정.

    반환: (PeriodSpec, next_ticker_krx) 또는 None (모두 완료/대기 상태).
    """
    today = today or datetime.now()
    watchlist_text = config.WATCHLIST_PATH.read_text(encoding="utf-8")
    watchlist = parse_watchlist(watchlist_text)

    for spec in _PERIODS:
        if not _is_deadline_passed(spec, today):
            continue  # 마감 전 PERIOD는 데이터 불완전
        next_ticker = _next_unfinished_ticker(spec, watchlist)
        if next_ticker is not None:
            return spec, next_ticker
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="활성 PERIOD + 다음 ticker 자동 선정"
    )
    parser.add_argument(
        "--format",
        choices=["csv", "shell"],
        default="csv",
        help="csv: 'period,year,reprt_code,ticker' / shell: 'PERIOD=... BSNS_YEAR=...'",
    )
    args = parser.parse_args()

    pick = pick_active_period()
    if pick is None:
        print("all-done: 모든 활성 PERIOD 24/24 완료 또는 다음 마감일 대기 중", file=sys.stderr)
        return 2

    spec, ticker = pick
    if args.format == "shell":
        print(
            f"PERIOD={spec.period_label} "
            f"BSNS_YEAR={spec.bsns_year} "
            f"REPRT_CODE={spec.reprt_code} "
            f"TICKER={ticker}"
        )
    else:
        print(f"{spec.period_label},{spec.bsns_year},{spec.reprt_code},{ticker}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
