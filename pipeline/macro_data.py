"""매크로 지표 fetch + 캐시 — KOSPI/KOSDAQ/USD-KRW/WTI 등.

페르소나의 매크로 의무 항목과 매치:
  - 환율 (원/달러)
  - 유가 (WTI)
  - 미국 금리 (10Y Treasury)
  - 외국인 매매는 별도 (KRX, 차후)

캐시: 1일 TTL JSON. cron 시점에 갱신.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


# (label, ticker_symbol, format_fn, prefix)
INDICATORS: list[tuple[str, str, str, str]] = [
    ("KOSPI", "^KS11", "{:,.2f}", ""),
    ("KOSPI 200", "^KS200", "{:,.2f}", ""),
    ("USD/KRW", "KRW=X", "{:,.2f}", "₩"),
    ("WTI", "CL=F", "{:,.2f}", "$"),
]


@dataclass(frozen=True)
class IndicatorSnapshot:
    label: str
    symbol: str
    latest: float
    latest_str: str
    change_1d: float | None
    change_pct_1d: float | None
    change_pct_1y: float | None
    sparkline: list[float]
    period_start: str
    period_end: str


def _safe_fetch(symbol: str, period: str = "1y", interval: str = "1d"):
    """yfinance fetch — 실패 시 None."""
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        hist = t.history(period=period, interval=interval, auto_adjust=True)
        if hist.empty:
            return None
        return hist
    except Exception as e:
        print(f"  [macro] fetch failed for {symbol}: {e}")
        return None


def fetch_indicator(label: str, symbol: str, fmt: str, prefix: str) -> IndicatorSnapshot | None:
    hist = _safe_fetch(symbol)
    if hist is None or len(hist) < 2:
        return None

    closes = [float(c) for c in hist["Close"].dropna().tolist()]
    if len(closes) < 2:
        return None

    latest = closes[-1]
    prev = closes[-2]
    change_1d = latest - prev
    change_pct_1d = (latest / prev - 1.0) * 100 if prev else None

    first = closes[0]
    change_pct_1y = (latest / first - 1.0) * 100 if first else None

    # 60-point sparkline (대략 최근 3개월)
    pts = closes[-60:] if len(closes) >= 60 else closes

    return IndicatorSnapshot(
        label=label,
        symbol=symbol,
        latest=latest,
        latest_str=prefix + fmt.format(latest),
        change_1d=change_1d,
        change_pct_1d=change_pct_1d,
        change_pct_1y=change_pct_1y,
        sparkline=pts,
        period_start=hist.index[0].strftime("%Y-%m-%d"),
        period_end=hist.index[-1].strftime("%Y-%m-%d"),
    )


def fetch_macro_snapshot() -> list[IndicatorSnapshot]:
    out: list[IndicatorSnapshot] = []
    for label, symbol, fmt, prefix in INDICATORS:
        snap = fetch_indicator(label, symbol, fmt, prefix)
        if snap is not None:
            out.append(snap)
    return out


def load_macro_snapshot(cache_path: Path, max_age_hours: int = 24) -> list[IndicatorSnapshot]:
    """캐시에서 로드, 없거나 stale이면 fresh fetch + 캐시 저장."""
    if cache_path.exists():
        age_h = (datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)).total_seconds() / 3600
        if age_h < max_age_hours:
            try:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
                return [IndicatorSnapshot(**d) for d in data]
            except (json.JSONDecodeError, TypeError) as e:
                print(f"  [macro] cache parse failed: {e}, re-fetching")

    snaps = fetch_macro_snapshot()
    if snaps:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps([asdict(s) for s in snaps], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return snaps
