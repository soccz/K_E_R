"""종목별 일별 외인 수급 — KRX primary + Naver fallback.

KRX 정보데이터시스템(data.krx.co.kr) → pykrx 인증 호출이 1순위(canonical).
KRX 인증 실패 또는 endpoint 깨짐 시 → Naver Finance HTML 스크레이프(fallback).

triggers (foreign_flow / decoupling)는 `fetch_foreign_flow(ticker, days)` 한 함수만 호출.
출처 정보는 `ForeignFlowDay.source`에 기록되어 추적 가능.

KRX 자격증명: .env의 KRX_ID, KRX_PW (선택 — 없으면 Naver 직행).
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup


# ════════════════════════════════════════════════════════════════════
# 공통 데이터 모델
# ════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ForeignFlowDay:
    """일별 외인 수급 — 출처 무관 공통 shape.

    필수: date, close, pct_change, foreign_net_krw, source
    옵션: 출처별 추가 정보 (None일 수 있음)
    """

    date: str  # YYYY-MM-DD
    close: int  # 종가 (KRW)
    pct_change: float  # 등락률 (%)
    volume: int  # 거래량 (주)
    foreign_net_krw: int  # 외인 순매매 KRW (canonical, KRX 매매대금 또는 주식수×종가)
    source: str  # "krx" | "naver"

    # 출처별 부가 정보 (없을 수 있음)
    foreign_net_shares: int | None = None  # Naver만 (KRX는 주식수 미제공)
    inst_net_krw: int | None = None  # KRX만 (Naver는 주식수만)
    foreign_holding_shares: int | None = None  # Naver만
    foreign_holding_pct: float | None = None  # Naver만


# ════════════════════════════════════════════════════════════════════
# KRX (primary) — pykrx 정식 매매대금
# ════════════════════════════════════════════════════════════════════


def _krx_credentials_set() -> bool:
    return bool(os.getenv("KRX_ID") and os.getenv("KRX_PW"))


def _fetch_krx(ticker: str, days: int) -> list[ForeignFlowDay]:
    """pykrx로 일별 외인 매매대금 + 종가/등락률 조회.

    pykrx의 get_market_trading_value_by_investor는 단일일 단위라 영업일 loop.
    OHLCV는 get_market_ohlcv_by_date로 한 번에 조회.
    """
    from pykrx import stock

    end = datetime.now()
    # 영업일 부족 방지: days × 1.6 캘린더일 buffer
    start = end - timedelta(days=int(days * 1.6) + 5)

    ohlcv = stock.get_market_ohlcv_by_date(
        start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), ticker
    )
    if ohlcv is None or ohlcv.empty:
        return []
    ohlcv = ohlcv.tail(days * 2)  # 충분한 영업일

    out: list[ForeignFlowDay] = []
    for idx, row in ohlcv.iterrows():
        ymd = idx.strftime("%Y%m%d")
        try:
            inv = stock.get_market_trading_value_by_investor(ymd, ymd, ticker)
        except Exception:
            continue
        if inv is None or inv.empty:
            continue
        try:
            foreign_krw = int(inv.loc["외국인", "순매수"])
            inst_krw = int(inv.loc["기관합계", "순매수"])
        except (KeyError, ValueError):
            continue

        close = int(row["종가"])
        prev_close = float(row.get("시가", close))
        pct = float(row.get("등락률", 0.0))
        volume = int(row.get("거래량", 0))
        out.append(
            ForeignFlowDay(
                date=idx.strftime("%Y-%m-%d"),
                close=close,
                pct_change=pct,
                volume=volume,
                foreign_net_krw=foreign_krw,
                source="krx",
                inst_net_krw=inst_krw,
            )
        )
        time.sleep(0.2)  # KRX rate limit 보호

    out.sort(key=lambda d: d.date, reverse=True)
    return out[:days]


# ════════════════════════════════════════════════════════════════════
# Naver (fallback) — HTML 스크레이프
# ════════════════════════════════════════════════════════════════════


_NAVER_BASE = "https://finance.naver.com/item/frgn.naver"
_NAVER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
_NAVER_RATE_SEC = 0.5


def _naver_int(s: str) -> int:
    s = s.replace(",", "").replace(" ", "")
    m = re.search(r"^[+-]?\d+$", s)
    return int(m.group(0)) if m else 0


def _naver_pct(s: str) -> float:
    s = s.replace(",", "").replace(" ", "").replace("%", "")
    m = re.search(r"^[+-]?\d+\.?\d*$", s)
    return float(m.group(0)) if m else 0.0


def _parse_naver_html(html: str) -> list[ForeignFlowDay]:
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table.type2 tr")
    out: list[ForeignFlowDay] = []
    for tr in rows:
        cells = tr.find_all("td")
        if len(cells) < 9:
            continue
        txts = [c.get_text(strip=True) for c in cells]
        if not txts[0] or "." not in txts[0]:
            continue
        try:
            close = _naver_int(txts[1])
            foreign_shares = _naver_int(txts[6])
            day = ForeignFlowDay(
                date=txts[0].replace(".", "-"),
                close=close,
                pct_change=_naver_pct(txts[3]),
                volume=_naver_int(txts[4]),
                foreign_net_krw=foreign_shares * close,  # 환산
                source="naver",
                foreign_net_shares=foreign_shares,
                foreign_holding_shares=_naver_int(txts[7]),
                foreign_holding_pct=_naver_pct(txts[8]),
            )
        except (ValueError, IndexError):
            continue
        out.append(day)
    return out


def _fetch_naver(ticker: str, days: int) -> list[ForeignFlowDay]:
    headers = {"User-Agent": _NAVER_UA, "Referer": "https://finance.naver.com/"}
    pages_needed = (days + 19) // 20
    all_days: list[ForeignFlowDay] = []
    for page in range(1, pages_needed + 1):
        url = f"{_NAVER_BASE}?code={ticker}&page={page}"
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200:
                break
            page_days = _parse_naver_html(r.text)
            if not page_days:
                break
            all_days.extend(page_days)
        except (requests.RequestException, ValueError):
            break
        if page < pages_needed:
            time.sleep(_NAVER_RATE_SEC)

    if not all_days:
        return []
    seen: set[str] = set()
    unique: list[ForeignFlowDay] = []
    for d in all_days:
        if d.date in seen:
            continue
        seen.add(d.date)
        unique.append(d)
    unique.sort(key=lambda d: d.date, reverse=True)
    return unique[:days]


# ════════════════════════════════════════════════════════════════════
# 통합 entry — KRX primary + Naver fallback + cache
# ════════════════════════════════════════════════════════════════════


_CACHE_DIR_DEFAULT = Path("pipeline/cache/foreign_flow")
_CACHE_TTL_SEC = 60 * 60 * 6  # 6h


def _cache_path(cache_dir: Path, ticker: str) -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    return cache_dir / f"{ticker}_{today}.json"


def _load_cache(path: Path, max_age_sec: int = _CACHE_TTL_SEC) -> list[ForeignFlowDay] | None:
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > max_age_sec:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [ForeignFlowDay(**d) for d in data]
    except (json.JSONDecodeError, TypeError):
        return None


def _save_cache(path: Path, days: list[ForeignFlowDay]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(d) for d in days], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def fetch_foreign_flow(
    ticker: str,
    days: int = 5,
    cache_dir: Path | None = None,
    use_cache: bool = True,
    prefer_krx: bool = True,
) -> list[ForeignFlowDay]:
    """종목별 일별 외인 수급 (최신 → 과거 순).

    1순위: KRX 정식 매매대금 (KRX_ID/KRX_PW 설정 시).
    2순위: Naver Finance HTML 스크레이프 (KRX 실패 또는 자격증명 없음).

    days: 반환할 영업일 수 (Naver 한 페이지 = 20영업일).
    cache_dir: 캐시 디렉토리. 미지정 시 pipeline/cache/foreign_flow.
    use_cache: 6시간 캐시 활성화 (기본 True).
    prefer_krx: True면 KRX 시도 후 실패 시 Naver. False면 바로 Naver.
    """
    if cache_dir is None:
        cache_dir = _CACHE_DIR_DEFAULT
    cache_path = _cache_path(cache_dir, ticker)

    if use_cache:
        cached = _load_cache(cache_path)
        if cached is not None and len(cached) >= days:
            return cached[:days]

    result: list[ForeignFlowDay] = []
    # 1순위 — KRX
    if prefer_krx and _krx_credentials_set():
        try:
            result = _fetch_krx(ticker, days)
        except Exception:
            result = []

    # 2순위 — Naver fallback
    if not result:
        try:
            result = _fetch_naver(ticker, days)
        except Exception:
            result = []

    if use_cache and result:
        _save_cache(cache_path, result)
    return result


def cumulative_foreign_krw(days: list[ForeignFlowDay], n: int = 3) -> int:
    """최근 N영업일 외인 순매매 누적 KRW (방향 부호 유지)."""
    return sum(d.foreign_net_krw for d in days[:n])


__all__ = [
    "ForeignFlowDay",
    "fetch_foreign_flow",
    "cumulative_foreign_krw",
]
