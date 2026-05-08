"""워치리스트 24종목 ticker_market 캐시 일괄 갱신.

매일 18:00 KST k_e_r-daily-refresh.timer가 호출 (장 마감 후 안정화 시점).
24종목 KRX OHLCV + DART stockTotqySttus 캐시를 한 번에 갱신.

site_renderer는 이 캐시만 읽어서 마스터 인덱스 표에 등락률·시총 표시 — fetch 비용
사이트 빌드와 분리.

CLI:
  python -m pipeline.bulk_ticker_refresh
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from pipeline import config
from pipeline.ticker_market_data import load_ticker_snapshot
from pipeline.watchlist_parser import parse_watchlist


def refresh_all(
    cache_dir: Path | None = None,
    bsns_year: int = 2025,
    reprt_code: str = "11011",
    force: bool = False,
) -> tuple[int, int, int]:
    """워치리스트 24종목 ticker_market 캐시 일괄 갱신.

    Args:
        cache_dir: 기본 pipeline/cache/. None이면 default.
        bsns_year: DART stockTotqySttus 조회 사업연도.
        reprt_code: DART 보고서 종류 (사업보고서=11011).
        force: True면 캐시 만료 무시하고 재fetch.

    Returns: (총 종목 수, 성공, 실패)
    """
    cache_dir = cache_dir or (config.REPO_ROOT / "pipeline" / "cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    watchlist = parse_watchlist(config.WATCHLIST_PATH.read_text(encoding="utf-8"))
    total = len(watchlist)
    ok = 0
    fail = 0

    print(f"[bulk-refresh] 워치리스트 {total}종목 ticker_market 캐시 갱신 시작")
    for i, entry in enumerate(watchlist, 1):
        cache_path = cache_dir / f"ticker_market_{entry.ticker}.json"
        if force and cache_path.exists():
            cache_path.unlink()
        try:
            snap = load_ticker_snapshot(
                cache_path,
                ticker_krx=entry.ticker,
                company_name=entry.name,
                corp_code=entry.corp_code,
                bsns_year=bsns_year,
                reprt_code=reprt_code,
                max_age_hours=24,  # 24h 캐시
            )
            mc = snap.market_cap_trillion_krw
            mc_str = f"{mc:.2f}조" if mc else "n/a"
            close_str = f"{snap.latest_close_krw:,.0f}" if snap.latest_close_krw else "n/a"
            print(f"  [{i:>2}/{total}] {entry.name:<20} 종가={close_str} 시총={mc_str}")
            ok += 1
        except Exception as e:
            print(f"  [{i:>2}/{total}] {entry.name:<20} FAIL: {e}")
            fail += 1
        # KRX rate limit 보호: 100ms
        time.sleep(0.1)

    print(f"[bulk-refresh] 완료 — {ok}/{total} 성공, {fail} 실패")
    return total, ok, fail


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="워치리스트 24종목 ticker_market 캐시 일괄 갱신")
    p.add_argument("--force", action="store_true", help="캐시 만료 무시하고 재fetch")
    p.add_argument("--bsns-year", type=int, default=2025)
    p.add_argument("--reprt-code", default="11011")
    args = p.parse_args()

    total, ok, fail = refresh_all(
        bsns_year=args.bsns_year,
        reprt_code=args.reprt_code,
        force=args.force,
    )
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
